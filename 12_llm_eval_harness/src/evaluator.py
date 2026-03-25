"""
LLM Eval Harness — Core Evaluator
Measures: faithfulness, relevance, hallucination rate, latency, cost-per-query

This is what OpenAI FDEs build when a customer says "the model isn't good enough."
You build evals, quantify failure modes, and bring data back to the research team.
"""

import json
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from openai import OpenAI

log = logging.getLogger(__name__)


# ── Eval Case ─────────────────────────────────────────────────────────────────

@dataclass
class EvalCase:
    """A single test case: question + context + expected answer."""
    id: str
    question: str
    context: str
    expected_answer: str
    tags: list[str] = field(default_factory=list)  # e.g. ["healthcare", "complex", "multi-hop"]


@dataclass
class EvalResult:
    case_id: str
    question: str
    context: str
    expected_answer: str
    actual_answer: str

    # Scores (0.0 - 1.0)
    faithfulness_score: float = 0.0     # Is the answer grounded in context? (no hallucination)
    relevance_score: float = 0.0        # Does it answer the question?
    completeness_score: float = 0.0     # Does it cover all key points?
    conciseness_score: float = 0.0      # Is it appropriately concise?

    # Derived
    hallucinated: bool = False          # faithfulness < 0.5
    passed: bool = False                # all core scores >= threshold

    # Operational metrics
    latency_ms: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    model: str = ""
    error: Optional[str] = None

    @property
    def composite_score(self) -> float:
        """Weighted composite: faithfulness most important for enterprise."""
        return (
            self.faithfulness_score * 0.4 +
            self.relevance_score    * 0.3 +
            self.completeness_score * 0.2 +
            self.conciseness_score  * 0.1
        )


# ── Evaluator ─────────────────────────────────────────────────────────────────

EVAL_PROMPT = """You are an expert evaluator for LLM-generated answers.
Score the answer on each dimension from 0.0 to 1.0.
Return ONLY valid JSON, no explanation.

Question: {question}
Context: {context}
Expected answer: {expected}
Actual answer: {actual}

Return JSON with this exact structure:
{{
  "faithfulness": <0.0-1.0>,     // Is every claim in the answer supported by the context?
  "relevance": <0.0-1.0>,        // Does the answer directly address the question?
  "completeness": <0.0-1.0>,     // Does it cover all key points from the expected answer?
  "conciseness": <0.0-1.0>,      // Is it appropriately concise (not too verbose)?
  "reasoning": "<one sentence explaining the most significant issue, if any>"
}}"""


class LLMEvaluator:
    """
    LLM-as-judge evaluator. Uses a separate model to score answers.

    Why LLM-as-judge:
    - Human eval doesn't scale; BLEU/ROUGE miss semantic similarity
    - LLM judges correlate well with human scores (Zheng et al., 2023)
    - Tradeoff: judge model can have its own biases; use deterministic prompts

    Best practice: use a different (ideally stronger) model as judge than
    the model being evaluated. e.g. evaluate gpt-4o-mini with gpt-4o.
    """

    def __init__(self, judge_model: str = "gpt-4o", pass_threshold: float = 0.7):
        self.client = OpenAI()
        self.judge_model = judge_model
        self.pass_threshold = pass_threshold

    def score(self, case: EvalCase, actual_answer: str,
              latency_ms: int = 0, tokens_used: int = 0,
              cost_usd: float = 0.0, model: str = "") -> EvalResult:

        result = EvalResult(
            case_id=case.id, question=case.question,
            context=case.context, expected_answer=case.expected_answer,
            actual_answer=actual_answer, latency_ms=latency_ms,
            tokens_used=tokens_used, cost_usd=cost_usd, model=model,
        )

        try:
            prompt = EVAL_PROMPT.format(
                question=case.question, context=case.context,
                expected=case.expected_answer, actual=actual_answer,
            )
            response = self.client.chat.completions.create(
                model=self.judge_model, temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            scores = json.loads(response.choices[0].message.content)

            result.faithfulness_score  = float(scores.get("faithfulness",  0))
            result.relevance_score     = float(scores.get("relevance",     0))
            result.completeness_score  = float(scores.get("completeness",  0))
            result.conciseness_score   = float(scores.get("conciseness",   0))
            result.hallucinated        = result.faithfulness_score < 0.5
            result.passed = all([
                result.faithfulness_score  >= self.pass_threshold,
                result.relevance_score     >= self.pass_threshold,
            ])

        except Exception as e:
            result.error = str(e)
            log.error(f"Eval failed for case {case.id}: {e}")

        return result


# ── Harness ───────────────────────────────────────────────────────────────────

@dataclass
class HarnessConfig:
    target_model: str = "gpt-4o-mini"
    judge_model: str = "gpt-4o"
    pass_threshold: float = 0.7
    temperature: float = 0.0
    max_tokens: int = 500
    save_results: bool = True
    results_dir: str = "reports"


class EvalHarness:
    """
    Runs a full eval suite and produces a report.

    Usage:
        harness = EvalHarness()
        cases = EvalHarness.load_cases("evals/healthcare_qa.json")
        report = harness.run(cases)
        harness.save_report(report)
    """

    def __init__(self, config: HarnessConfig = None):
        self.config = config or HarnessConfig()
        self.client = OpenAI()
        self.evaluator = LLMEvaluator(
            judge_model=self.config.judge_model,
            pass_threshold=self.config.pass_threshold,
        )

    def _generate_answer(self, case: EvalCase) -> tuple[str, int, int, float]:
        """Run the target model on a case. Returns (answer, latency_ms, tokens, cost)."""
        t0 = time.time()
        response = self.client.chat.completions.create(
            model=self.config.target_model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            messages=[
                {"role": "system", "content": "Answer based only on the provided context."},
                {"role": "user", "content": f"Context:\n{case.context}\n\nQuestion: {case.question}"},
            ],
        )
        latency_ms = int((time.time() - t0) * 1000)
        tokens = response.usage.total_tokens
        cost = tokens * 15e-6  # gpt-4o-mini pricing
        return response.choices[0].message.content, latency_ms, tokens, cost

    def run(self, cases: list[EvalCase]) -> dict:
        """Run all eval cases and return a full report."""
        results = []
        log.info(f"Running eval: {len(cases)} cases, model={self.config.target_model}")

        for i, case in enumerate(cases):
            log.info(f"  [{i+1}/{len(cases)}] case_id={case.id}")
            try:
                answer, latency_ms, tokens, cost = self._generate_answer(case)
                result = self.evaluator.score(
                    case, answer, latency_ms, tokens, cost, self.config.target_model
                )
            except Exception as e:
                result = EvalResult(
                    case_id=case.id, question=case.question, context=case.context,
                    expected_answer=case.expected_answer, actual_answer="",
                    error=str(e),
                )
                log.error(f"Case {case.id} failed: {e}")
            results.append(result)

        return self._build_report(results)

    def _build_report(self, results: list[EvalResult]) -> dict:
        valid = [r for r in results if not r.error]
        n = len(valid)
        if n == 0:
            return {"error": "All cases failed", "results": []}

        return {
            "summary": {
                "total_cases": len(results),
                "valid_cases": n,
                "pass_rate": round(sum(r.passed for r in valid) / n, 3),
                "hallucination_rate": round(sum(r.hallucinated for r in valid) / n, 3),
                "avg_faithfulness":   round(sum(r.faithfulness_score  for r in valid) / n, 3),
                "avg_relevance":      round(sum(r.relevance_score     for r in valid) / n, 3),
                "avg_completeness":   round(sum(r.completeness_score  for r in valid) / n, 3),
                "avg_composite":      round(sum(r.composite_score     for r in valid) / n, 3),
                "avg_latency_ms":     round(sum(r.latency_ms          for r in valid) / n),
                "p95_latency_ms":     sorted(r.latency_ms for r in valid)[int(n * 0.95)],
                "total_cost_usd":     round(sum(r.cost_usd            for r in results), 5),
                "cost_per_query_usd": round(sum(r.cost_usd            for r in valid) / n, 6),
                "model": self.config.target_model,
                "judge": self.config.judge_model,
            },
            "results": [self._result_to_dict(r) for r in results],
            "failed_cases": [r.case_id for r in results if r.error],
        }

    @staticmethod
    def _result_to_dict(r: EvalResult) -> dict:
        return {
            "case_id": r.case_id, "passed": r.passed,
            "hallucinated": r.hallucinated, "composite_score": r.composite_score,
            "scores": {
                "faithfulness": r.faithfulness_score, "relevance": r.relevance_score,
                "completeness": r.completeness_score, "conciseness": r.conciseness_score,
            },
            "latency_ms": r.latency_ms, "cost_usd": r.cost_usd,
            "error": r.error,
        }

    def save_report(self, report: dict, filename: str = None) -> str:
        Path(self.config.results_dir).mkdir(exist_ok=True)
        if not filename:
            import datetime
            filename = f"eval_{self.config.target_model.replace('/','_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = Path(self.config.results_dir) / filename
        path.write_text(json.dumps(report, indent=2))
        log.info(f"Report saved: {path}")
        return str(path)

    @staticmethod
    def load_cases(path: str) -> list[EvalCase]:
        data = json.loads(Path(path).read_text())
        return [EvalCase(**c) for c in data]
