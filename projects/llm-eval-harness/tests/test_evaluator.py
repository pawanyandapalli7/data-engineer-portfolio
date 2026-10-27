"""
LLM Eval Harness — Unit Tests
Covers scoring math, LLM-as-judge parsing (mocked), report aggregation,
and eval case loading. No API calls or keys required.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evaluator import EvalCase, EvalHarness, EvalResult, HarnessConfig, LLMEvaluator

# ── EvalResult.composite_score ───────────────────────────────────────────────


class TestCompositeScore:
    def test_perfect_scores_give_composite_one(self):
        r = EvalResult(
            case_id="c1",
            question="q",
            context="ctx",
            expected_answer="e",
            actual_answer="a",
            faithfulness_score=1.0,
            relevance_score=1.0,
            completeness_score=1.0,
            conciseness_score=1.0,
        )
        assert r.composite_score == pytest.approx(1.0)

    def test_weights_faithfulness_most_heavily(self):
        # All faithfulness, nothing else -> should equal the faithfulness weight (0.4)
        r = EvalResult(
            case_id="c1",
            question="q",
            context="ctx",
            expected_answer="e",
            actual_answer="a",
            faithfulness_score=1.0,
            relevance_score=0.0,
            completeness_score=0.0,
            conciseness_score=0.0,
        )
        assert r.composite_score == pytest.approx(0.4)

    def test_zero_scores_give_zero_composite(self):
        r = EvalResult(
            case_id="c1",
            question="q",
            context="ctx",
            expected_answer="e",
            actual_answer="a",
        )
        assert r.composite_score == 0.0


# ── LLMEvaluator.score (mocked OpenAI judge) ─────────────────────────────────


class TestLLMEvaluatorScore:
    def _mock_client_returning(self, scores_dict):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=json.dumps(scores_dict)))]
        mock_client.chat.completions.create.return_value = mock_response
        return mock_client

    def test_passing_case_marked_passed(self):
        case = EvalCase(id="c1", question="q", context="ctx", expected_answer="e")
        with patch("evaluator.OpenAI") as mock_openai:
            mock_openai.return_value = self._mock_client_returning(
                {
                    "faithfulness": 0.9,
                    "relevance": 0.9,
                    "completeness": 0.8,
                    "conciseness": 0.8,
                }
            )
            evaluator = LLMEvaluator(pass_threshold=0.7)
            result = evaluator.score(case, "some answer")

        assert result.passed is True
        assert result.hallucinated is False
        assert result.error is None

    def test_low_faithfulness_marks_hallucinated_and_failed(self):
        case = EvalCase(id="c1", question="q", context="ctx", expected_answer="e")
        with patch("evaluator.OpenAI") as mock_openai:
            mock_openai.return_value = self._mock_client_returning(
                {
                    "faithfulness": 0.2,
                    "relevance": 0.9,
                    "completeness": 0.8,
                    "conciseness": 0.8,
                }
            )
            evaluator = LLMEvaluator(pass_threshold=0.7)
            result = evaluator.score(case, "some answer")

        assert result.hallucinated is True
        assert result.passed is False

    def test_judge_call_failure_sets_error_not_exception(self):
        case = EvalCase(id="c1", question="q", context="ctx", expected_answer="e")
        with patch("evaluator.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = RuntimeError("API down")
            mock_openai.return_value = mock_client

            evaluator = LLMEvaluator()
            result = evaluator.score(case, "some answer")

        assert result.error is not None
        assert "API down" in result.error
        assert result.passed is False  # default, never set to True on error


# ── EvalHarness._build_report ─────────────────────────────────────────────────


class TestBuildReport:
    def _make_result(self, case_id, faithfulness, relevance, passed, latency_ms, cost, error=None):
        r = EvalResult(
            case_id=case_id,
            question="q",
            context="ctx",
            expected_answer="e",
            actual_answer="a",
            faithfulness_score=faithfulness,
            relevance_score=relevance,
            passed=passed,
            latency_ms=latency_ms,
            cost_usd=cost,
            error=error,
        )
        return r

    def test_report_aggregates_valid_cases_only(self):
        with patch("evaluator.OpenAI"):
            harness = EvalHarness(HarnessConfig())

        results = [
            self._make_result("c1", 0.9, 0.9, True, 300, 0.001),
            self._make_result("c2", 0.9, 0.9, True, 500, 0.001),
            self._make_result("c3", 0.0, 0.0, False, 0, 0.0, error="failed"),
        ]
        report = harness._build_report(results)

        assert report["summary"]["total_cases"] == 3
        assert report["summary"]["valid_cases"] == 2  # c3 excluded from averages
        assert report["summary"]["pass_rate"] == 1.0
        assert report["failed_cases"] == ["c3"]

    def test_report_all_cases_failed(self):
        with patch("evaluator.OpenAI"):
            harness = EvalHarness(HarnessConfig())

        results = [self._make_result("c1", 0, 0, False, 0, 0, error="boom")]
        report = harness._build_report(results)

        assert "error" in report
        assert report["results"] == []


# ── EvalHarness.load_cases ────────────────────────────────────────────────────


class TestLoadCases:
    def test_loads_cases_from_json(self, tmp_path):
        data = [
            {"id": "c1", "question": "q1", "context": "ctx1", "expected_answer": "e1"},
            {"id": "c2", "question": "q2", "context": "ctx2", "expected_answer": "e2", "tags": ["healthcare"]},
        ]
        f = tmp_path / "cases.json"
        f.write_text(json.dumps(data))

        cases = EvalHarness.load_cases(str(f))

        assert len(cases) == 2
        assert cases[0].id == "c1"
        assert cases[1].tags == ["healthcare"]

    def test_loads_real_healthcare_eval_file(self):
        """Sanity check against the actual eval set shipped in this module."""
        eval_file = Path(__file__).resolve().parents[1] / "evals" / "healthcare_qa.json"
        cases = EvalHarness.load_cases(str(eval_file))

        assert len(cases) == 6  # keep the README in sync with this number
        assert all(c.question and c.context and c.expected_answer for c in cases)


# ── Separate hallucination flag, groundedness, percentiles ───────────────────


class TestJudgeHallucinationFlag:
    def _score(self, scores):
        case = EvalCase(id="c1", question="q", context="ctx", expected_answer="e")
        with patch("evaluator.OpenAI") as mock_openai:
            mock_openai.return_value = TestLLMEvaluatorScore()._mock_client_returning(scores)
            return LLMEvaluator(pass_threshold=0.7).score(case, "some answer")

    def test_judge_flag_fails_case_even_with_high_faithfulness(self):
        r = self._score({"faithfulness": 0.8, "relevance": 0.9, "hallucination": True})
        assert r.hallucinated is True and r.passed is False

    def test_string_false_is_not_treated_as_true(self):
        r = self._score({"faithfulness": 0.9, "relevance": 0.9, "hallucination": "false"})
        assert r.hallucinated is False and r.passed is True


class TestLexicalGroundedness:
    def test_fully_grounded(self):
        from evaluator import lexical_groundedness

        assert lexical_groundedness("Reviews take 30 business days.", "Standard reviews take 30 business days.") == 1.0

    def test_invented_terms_lower_the_score(self):
        from evaluator import lexical_groundedness

        assert (
            lexical_groundedness("Reviews take 90 calendar weeks.", "Reviews take 30 business days.") == 0.4
        )  # 2 of 5 terms

    def test_empty_answer(self):
        from evaluator import lexical_groundedness

        assert lexical_groundedness("", "anything") == 0.0


class TestPercentile:
    def test_nearest_rank(self):
        from evaluator import percentile

        values = [100, 200, 300, 400, 500, 600]
        assert percentile(values, 50) == 300
        assert percentile(values, 95) == 600
        assert percentile([], 95) == 0.0


class TestCost:
    def test_cost_uses_model_rates(self):
        from pricing import cost_usd

        assert cost_usd("gpt-4o", 1000, 1000) == pytest.approx(0.0125)


class TestRetrievalMetrics:
    def test_metrics_on_known_ranking(self):
        from retrieval_metrics import precision_at_k, recall_at_k, reciprocal_rank, summarize

        retrieved = ["a", "x", "b", "y", "z"]
        relevant = {"a", "b", "c"}
        assert precision_at_k(retrieved, relevant, 5) == pytest.approx(0.4)
        assert recall_at_k(retrieved, relevant, 5) == pytest.approx(2 / 3)
        assert reciprocal_rank(["x", "a"], relevant) == 0.5
        s = summarize([(retrieved, relevant), (["q"], {"a"})], k=5)
        assert s["queries"] == 2 and s["hit_rate@5"] == 0.5 and s["mrr"] == 0.5
