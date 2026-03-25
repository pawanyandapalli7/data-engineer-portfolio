"""
Model Comparison — run the same eval suite across multiple models
and produce a side-by-side comparison report.

This is exactly what Mool AI's Experimentation Engine does at enterprise scale.
"""

import json
import logging
from pathlib import Path

from evaluator import EvalHarness, HarnessConfig

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


MODELS_TO_COMPARE = [
    "gpt-4o-mini",    # cheapest, fastest
    "gpt-4o",         # best quality, slower, more expensive
]

EVAL_FILE = "evals/healthcare_qa.json"
JUDGE_MODEL = "gpt-4o"


def run_comparison():
    cases = EvalHarness.load_cases(EVAL_FILE)
    log.info(f"Loaded {len(cases)} eval cases from {EVAL_FILE}")

    model_reports = {}
    for model in MODELS_TO_COMPARE:
        log.info(f"\n{'='*50}\nEvaluating: {model}\n{'='*50}")
        config = HarnessConfig(
            target_model=model,
            judge_model=JUDGE_MODEL,
            pass_threshold=0.7,
        )
        harness = EvalHarness(config)
        report = harness.run(cases)
        model_reports[model] = report
        harness.save_report(report, f"eval_{model.replace('/','_')}.json")

    # Build comparison table
    comparison = {
        "models_compared": MODELS_TO_COMPARE,
        "judge_model": JUDGE_MODEL,
        "eval_file": EVAL_FILE,
        "comparison": {},
    }

    metrics = [
        "pass_rate", "hallucination_rate",
        "avg_faithfulness", "avg_relevance", "avg_composite",
        "avg_latency_ms", "p95_latency_ms",
        "cost_per_query_usd", "total_cost_usd",
    ]

    for metric in metrics:
        comparison["comparison"][metric] = {
            model: model_reports[model]["summary"].get(metric)
            for model in MODELS_TO_COMPARE
        }

    # Recommendation logic
    best_quality = max(MODELS_TO_COMPARE, key=lambda m: model_reports[m]["summary"]["avg_composite"])
    best_cost    = min(MODELS_TO_COMPARE, key=lambda m: model_reports[m]["summary"]["cost_per_query_usd"])
    fastest      = min(MODELS_TO_COMPARE, key=lambda m: model_reports[m]["summary"]["avg_latency_ms"])

    comparison["recommendation"] = {
        "best_quality": best_quality,
        "best_cost_efficiency": best_cost,
        "fastest": fastest,
        "note": (
            f"If cost < $0.001/query is acceptable, use {best_cost}. "
            f"For highest accuracy, use {best_quality}. "
            f"Hallucination rate difference: "
            f"{abs(model_reports[MODELS_TO_COMPARE[0]]['summary']['hallucination_rate'] - model_reports[MODELS_TO_COMPARE[1]]['summary']['hallucination_rate']):.3f}"
        ),
    }

    out_path = Path("reports/model_comparison.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(comparison, indent=2))
    log.info(f"\nComparison saved to {out_path}")

    # Print summary table
    print("\n" + "="*70)
    print(f"{'Metric':<30} " + " ".join(f"{m:<18}" for m in MODELS_TO_COMPARE))
    print("-"*70)
    for metric in metrics:
        vals = [str(comparison["comparison"][metric].get(m, "N/A")) for m in MODELS_TO_COMPARE]
        print(f"{metric:<30} " + " ".join(f"{v:<18}" for v in vals))
    print("="*70)
    print(f"Best quality:        {best_quality}")
    print(f"Best cost:           {best_cost}")
    print(f"Fastest:             {fastest}")

    return comparison


if __name__ == "__main__":
    run_comparison()
