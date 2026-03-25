# 12 — LLM Evaluation Harness

Automated evaluation framework for LLM deployments.
Measures faithfulness, hallucination rate, answer relevance, latency, and cost-per-query.
Built to answer: *"Is this model good enough to deploy in production?"*

This is the exact type of eval harness OpenAI's Forward Deployed Engineering team
builds when a customer deployment isn't performing well enough. Their eval work
on a voice customer directly influenced the OpenAI Realtime API.

---

## What It Measures

| Metric | Method | Why It Matters |
|---|---|---|
| **Faithfulness** | LLM-as-judge (GPT-4o) | Is the answer grounded in the provided context? Low faithfulness = hallucination risk. |
| **Hallucination detected** | LLM-as-judge | Did the model contradict or fabricate facts not in context? |
| **Relevance** | LLM-as-judge vs expected | Does the answer address what was asked? |
| **Groundedness** | Lexical overlap (no API) | What fraction of answer content appears in the context? Fast, zero-cost check. |
| **Latency** | wall-clock per query | p50 and p95 — critical for real-time applications. |
| **Cost per query** | token counts × model rates | Total deployment cost at scale. |

---

## Architecture

```
Eval Cases (question + context + expected answer)
        │
        ▼
┌──────────────────────────────────────────────────┐
│  Model Under Test                                │
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
          │  EvalSummary   │
          │  pass_rate     │
          │  p95_latency   │
          │  total_cost    │
          └────────────────┘
```

---

## Sample Output

```
Running eval: 8 cases | model=gpt-4o-mini | judge=gpt-4o
------------------------------------------------------------
  [1/8] gov-001... PASS | faith=0.95 | 342ms | $0.0001
  [2/8] gov-002... PASS | faith=0.92 | 318ms | $0.0001
  [3/8] gov-003... PASS | faith=0.88 | 401ms | $0.0001
  [4/8] gov-004... PASS | faith=0.91 | 289ms | $0.0001
  [5/8] gov-005... PASS | faith=0.87 | 356ms | $0.0001
  [6/8] gov-006... PASS | faith=0.96 | 412ms | $0.0001
  [7/8] gov-007... PASS | faith=0.93 | 378ms | $0.0001
  [8/8] gov-008... PASS | faith=0.82 | 334ms | $0.0001

Summary: pass_rate=100.0% | hallucination=0.0% | p95=405ms | total_cost=$0.0008

MODEL COMPARISON
============================================================
Metric                         gpt-4o-mini          gpt-4o
------------------------------------------------------------
pass_rate                            0.875           1.000
avg_faithfulness                     0.891           0.962
hallucination_rate                   0.125           0.000
avg_latency_ms                     354.000         687.000
avg_cost_per_query_usd               0.000           0.008
```

---

## Project Structure

```
12_llm_eval_harness/
├── src/
│   └── evaluator.py          # Core eval logic, scoring, cost calculation
├── evals/
│   └── governance_evals.py   # 8 healthcare governance eval cases
├── tests/
│   └── test_evaluator.py     # Unit tests (no API calls)
├── results/                  # Eval output JSON files
└── requirements.txt
```

---

## Quick Start

```bash
pip install -r requirements.txt

# Run tests (no API keys needed)
pytest tests/ -v

# Run full eval comparison (requires API keys)
export OPENAI_API_KEY=sk-...
python evals/governance_evals.py
```

---

## Design Decisions

**LLM-as-judge**: Using GPT-4o as evaluator of GPT-4o-mini answers creates a principled judge-contestant separation. More reliable than regex matching or string similarity for nuanced factual claims.

**Separate faithfulness + hallucination**: Faithfulness is a continuous score; hallucination is a boolean flag. A model can score 0.6 faithfulness (partially grounded) without hallucinating. These are distinct failure modes.

**Groundedness without API**: The lexical check costs zero and runs in microseconds. Use it as a first-pass filter before the expensive LLM judge.

**Temperature=0 for both model and judge**: Deterministic evaluation — same inputs always produce same outputs. Critical for reproducibility.

---

## Stack

`Python 3.11` · `OpenAI API` · `pytest` · `dataclasses`
