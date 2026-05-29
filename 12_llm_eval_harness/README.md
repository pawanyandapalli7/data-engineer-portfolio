# 12 — LLM Evaluation Harness

> Automated framework to answer: *"Is this model safe to deploy in production?"*  
> Measures faithfulness, hallucination rate, answer relevance, latency, and cost-per-query.

**Stack:** `Python 3.11` · `OpenAI API` · `pytest` · `dataclasses`

---

## Why This Exists

Shipping an LLM to production without evals is guesswork. This harness answers four questions before any deployment decision:

1. **Is the model hallucinating?** (faithfulness < 0.5 = flagged)
2. **Does it answer the actual question?** (relevance score)
3. **What does quality cost?** (cost-per-query at scale)
4. **Is the difference between Model A and Model B worth the price?** (comparison report)

This is the same type of work OpenAI's Forward Deployed Engineering team does when a customer deployment underperforms. Build evals, quantify failure modes, bring data back to the team.

---

## What It Measures

| Metric | Method | Why It Matters |
|---|---|---|
| **Faithfulness** | LLM-as-judge (GPT-4o) | Is the answer grounded in context? Low faithfulness = hallucination risk. |
| **Hallucination detected** | LLM-as-judge | Did the model contradict or fabricate facts? |
| **Relevance** | LLM-as-judge vs expected | Does the answer address what was asked? |
| **Groundedness** | Lexical overlap | Fraction of answer content appearing in context. Zero API cost. |
| **Latency** | wall-clock per query | p50 and p95 — critical for real-time applications. |
| **Cost per query** | token counts × rates | Total deployment cost at scale. |

---

## Sample Output

```
Running eval: 8 cases | model=gpt-4o-mini | judge=gpt-4o
────────────────────────────────────────────────────────────
  [1/8] hc_001... PASS | faith=0.95 | 342ms | $0.0001
  [2/8] hc_002... PASS | faith=0.92 | 318ms | $0.0001
  [3/8] hc_003... PASS | faith=0.88 | 401ms | $0.0001
  ...

Summary: pass_rate=87.5% | hallucination=12.5% | p95=405ms | total_cost=$0.0008

MODEL COMPARISON
════════════════════════════════════════════════════════════
Metric                        gpt-4o-mini        gpt-4o
────────────────────────────────────────────────────────────
pass_rate                           0.875          1.000
avg_faithfulness                    0.891          0.962
hallucination_rate                  0.125          0.000
avg_latency_ms                    354.000        687.000
cost_per_query_usd                  0.000          0.008
════════════════════════════════════════════════════════════
Recommendation: gpt-4o-mini for cost-sensitive workloads.
                gpt-4o for zero-hallucination requirements.
```

---

## Architecture

```
Eval Cases (question + context + expected answer)
        │
        ▼
┌──────────────────────────────────────────────────┐
│  Model Under Test (configurable)                 │
│  Generate answer using only provided context     │
└──────────────────┬───────────────────────────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
┌──────────────────┐ ┌──────────────────┐
│  LLM Judge       │ │  Lexical Scorer  │
│  (GPT-4o)        │ │  (zero API cost) │
│  Faithfulness    │ │  Groundedness    │
│  Relevance       │ │                  │
│  Hallucination   │ │                  │
└────────┬─────────┘ └────────┬─────────┘
         └────────────────────┘
                   │
                   ▼
          ┌────────────────┐
          │  EvalSummary   │  pass_rate · p95_latency · total_cost
          └────────────────┘
```

---

## Design Decisions

**LLM-as-judge vs BLEU/ROUGE** — BLEU/ROUGE miss semantic similarity entirely. A judge model correlates far better with human scores (Zheng et al., 2023). Using GPT-4o to evaluate GPT-4o-mini creates principled judge-contestant separation.

**Faithfulness ≠ Hallucination** — Faithfulness is continuous (0.0–1.0). Hallucination is a boolean flag. A model can score 0.6 faithfulness (partially grounded) without technically hallucinating. These are distinct failure modes requiring different mitigations.

**Lexical groundedness check** — Zero-cost first-pass filter. Runs in microseconds. Use it to skip the expensive LLM judge call for obviously ungrounded answers.

**Temperature=0 for both model and judge** — Same inputs always produce same outputs. Critical for reproducibility and debugging regressions between model versions.

---

## Project Structure

```
12_llm_eval_harness/
├── src/
│   ├── evaluator.py          # EvalHarness, LLMEvaluator, scoring logic
│   └── compare_models.py     # Side-by-side model comparison report
├── evals/
│   └── healthcare_qa.json    # 6 healthcare eval cases with expected answers
├── tests/
│   └── test_evaluator.py     # Unit tests — no API calls required
└── requirements.txt
```

---

## Quick Start

```bash
pip install -r requirements.txt

# Run tests (no API keys needed)
pytest tests/ -v

# Run eval on a single model
export OPENAI_API_KEY=sk-...
python -c "
from src.evaluator import EvalHarness, HarnessConfig
cases = EvalHarness.load_cases('evals/healthcare_qa.json')
harness = EvalHarness(HarnessConfig(target_model='gpt-4o-mini'))
report = harness.run(cases)
harness.save_report(report)
"

# Run model comparison (gpt-4o-mini vs gpt-4o)
python src/compare_models.py
```

---

## Extending the Harness

**Add new eval cases** — Drop JSON into `evals/`. Each case needs `id`, `question`, `context`, `expected_answer`.

**Add new metrics** — Subclass `LLMEvaluator` and extend the `EVAL_PROMPT`. New scores automatically flow through to the report.

**Change the judge** — Set `HarnessConfig(judge_model="claude-opus-4")`. Any OpenAI-compatible endpoint works.

**CI integration** — Run `pytest tests/` in CI with no keys. Run the full eval in a weekly scheduled job to catch regressions between model version upgrades.

---

## Related

`11_rag_pipeline/` — The RAG system this harness was built to evaluate. The healthcare eval cases (`evals/healthcare_qa.json`) directly test RAG retrieval quality on medical governance documents.
