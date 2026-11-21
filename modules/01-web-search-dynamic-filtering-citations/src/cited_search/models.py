"""Models you can pick, their prices, and a cost estimate for a run.

Prices are the Claude API list prices (USD per million tokens) as of
November 2026. Check https://claude.com/pricing before relying on them.

Web search is billed per search on top of tokens, at the same price on every
model. With Haiku, searches are most of the bill.
"""

from dataclasses import dataclass
from typing import Any

DEFAULT_MODEL = "claude-haiku-5-5"
PRICE_PER_SEARCH = 10 / 1_000
TOKENS_PER_PRICE_UNIT = 1_000_000


@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    input_price: float  # USD per million input tokens
    output_price: float  # USD per million output tokens
    # Server-side refusal fallbacks (fallbacks="default") exist for Opus and
    # Sonnet. Haiku 5.5 has no server-side fallback, so we don't send them.
    supports_fallbacks: bool


MODELS: dict[str, ModelInfo] = {
    # Haiku 5.5 price is for prompts up to 100K tokens ($0.50 / $2.50 beyond).
    "claude-haiku-5-5": ModelInfo("claude-haiku-5-5", 0.10, 0.50, supports_fallbacks=False),
    "claude-sonnet-5-5": ModelInfo("claude-sonnet-5-5", 2.00, 10.00, supports_fallbacks=True),
    "claude-opus-5-5": ModelInfo("claude-opus-5-5", 4.00, 20.00, supports_fallbacks=True),
}


@dataclass(frozen=True)
class Cost:
    tokens: float
    searches: float

    @property
    def total(self) -> float:
        return self.tokens + self.searches


def get_model(model_id: str) -> ModelInfo:
    if model_id not in MODELS:
        raise ValueError(f"unknown model {model_id!r}, pick one of: {', '.join(MODELS)}")
    return MODELS[model_id]


def estimate_cost(usage: Any, model_id: str) -> Cost:
    """Estimate the USD cost of a run from its usage (input/output tokens and searches)."""
    model = get_model(model_id)
    tokens = (
        usage.input_tokens * model.input_price + usage.output_tokens * model.output_price
    ) / TOKENS_PER_PRICE_UNIT
    return Cost(tokens=tokens, searches=usage.web_search_requests * PRICE_PER_SEARCH)
