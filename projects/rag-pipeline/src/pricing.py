"""Per-token list prices (USD per 1M tokens) used for cost reporting.

These are list prices at the time of writing and change over time; override
them with the RAG_PRICES_JSON env var (same shape) instead of trusting them.
"""

import json
import os

_DEFAULT = {
    # chat models: input / output
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    # embedding models: input only
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
    "text-embedding-3-large": {"input": 0.13, "output": 0.0},
}

PRICES = {**_DEFAULT, **json.loads(os.environ.get("RAG_PRICES_JSON", "{}"))}


def cost_usd(model: str, input_tokens: int, output_tokens: int = 0) -> float:
    """Cost of one call. Unknown models cost 0.0 rather than a made-up number."""
    p = PRICES.get(model)
    if not p:
        return 0.0
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000
