import pytest

from cited_search.models import MODELS, estimate_cost, get_model
from cited_search.search import Usage


def test_knows_the_three_current_models():
    assert set(MODELS) == {"claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"}


def test_rejects_an_unknown_model():
    with pytest.raises(ValueError, match="claude-gpt"):
        get_model("claude-gpt")


def test_search_cost_is_the_same_on_every_model():
    usage = Usage(input_tokens=0, output_tokens=0, web_search_requests=3)

    costs = {model_id: estimate_cost(usage, model_id).searches for model_id in MODELS}

    assert list(costs.values()) == [pytest.approx(0.03)] * len(MODELS)


def test_token_cost_uses_the_model_price():
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000, web_search_requests=0)

    assert estimate_cost(usage, "claude-haiku-5-5").tokens == pytest.approx(0.10 + 0.50)
    assert estimate_cost(usage, "claude-sonnet-5-5").tokens == pytest.approx(2 + 10)
    assert estimate_cost(usage, "claude-opus-5-5").tokens == pytest.approx(4 + 20)


def test_total_adds_tokens_and_searches():
    usage = Usage(input_tokens=20_000, output_tokens=1_000, web_search_requests=2)

    cost = estimate_cost(usage, "claude-haiku-5-5")

    assert cost.total == pytest.approx(0.002 + 0.0005 + 0.02)
