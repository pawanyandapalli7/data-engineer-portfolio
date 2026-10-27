"""Retrieval metrics for a RAG system: did the right chunks come back?

The answer-quality harness (evaluator.py) hands the model the ideal context, so
it measures generation only. These functions measure the retrieval step, given
labelled data: for each question, the ids of the chunks that answer it.

    results = [(retrieved_ids_in_rank_order, relevant_ids), ...]
    summarize(results, k=5)
    -> {"precision@5": ..., "recall@5": ..., "mrr": ..., "hit_rate@5": ..., "queries": n}
"""

from typing import Iterable, Sequence


def precision_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    top = list(retrieved)[:k]
    if not top:
        return 0.0
    rel = set(relevant)
    return sum(r in rel for r in top) / len(top)


def recall_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    rel = set(relevant)
    if not rel:
        return 0.0
    return len(rel & set(list(retrieved)[:k])) / len(rel)


def reciprocal_rank(retrieved: Sequence[str], relevant: Iterable[str]) -> float:
    rel = set(relevant)
    for i, r in enumerate(retrieved, start=1):
        if r in rel:
            return 1.0 / i
    return 0.0


def summarize(results: Sequence[tuple[Sequence[str], Iterable[str]]], k: int = 5) -> dict:
    results = [(list(ret), set(rel)) for ret, rel in results]
    n = len(results)
    if n == 0:
        return {"queries": 0}
    return {
        "queries": n,
        f"precision@{k}": round(sum(precision_at_k(r, g, k) for r, g in results) / n, 3),
        f"recall@{k}": round(sum(recall_at_k(r, g, k) for r, g in results) / n, 3),
        f"hit_rate@{k}": round(sum(bool(set(r[:k]) & g) for r, g in results) / n, 3),
        "mrr": round(sum(reciprocal_rank(r, g) for r, g in results) / n, 3),
    }
