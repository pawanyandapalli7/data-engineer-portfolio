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

from evaluator import EvalCase, EvalResult, LLMEvaluator, EvalHarness, HarnessConfig


# ── EvalResult.composite_score ───────────────────────────────────────────────

class TestCompositeScore:

    def test_perfect_scores_give_composite_one(self):
        r = EvalResult(
            case_id="c1", question="q", context="ctx", expected_answer="e", actual_answer="a",
            faithfulness_score=1.0, relevance_score=1.0, completeness_score=1.0, conciseness_score=1.0,
        )
        assert r.composite_score == pytest.approx(1.0)

    def test_weights_faithfulness_most_heavily(self):
        # All faithfulness, nothing else -> should equal the faithfulness weight (0.4)
        r = EvalResult(
            case_id="c1", question="q", context="ctx", expected_answer="e", actual_answer="a",
            faithfulness_score=1.0, relevance_score=0.0, completeness_score=0.0, conciseness_score=0.0,
        )
        assert r.composite_score == pytest.approx(0.4)

    def test_zero_scores_give_zero_composite(self):
        r = EvalResult(
            case_id="c1", question="q", context="ctx", expected_answer="e", actual_answer="a",
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
            mock_openai.return_value = self._mock_client_returning({
                "faithfulness": 0.9, "relevance": 0.9, "completeness": 0.8, "conciseness": 0.8,
            })
            evaluator = LLMEvaluator(pass_threshold=0.7)
            result = evaluator.score(case, "some answer")

        assert result.passed is True
        assert result.hallucinated is False
        assert result.error is None

    def test_low_faithfulness_marks_hallucinated_and_failed(self):
        case = EvalCase(id="c1", question="q", context="ctx", expected_answer="e")
        with patch("evaluator.OpenAI") as mock_openai:
            mock_openai.return_value = self._mock_client_returning({
                "faithfulness": 0.2, "relevance": 0.9, "completeness": 0.8, "conciseness": 0.8,
            })
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
            case_id=case_id, question="q", context="ctx", expected_answer="e", actual_answer="a",
            faithfulness_score=faithfulness, relevance_score=relevance,
            passed=passed, latency_ms=latency_ms, cost_usd=cost, error=error,
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

        assert len(cases) == 6
        assert all(c.question and c.context and c.expected_answer for c in cases)
