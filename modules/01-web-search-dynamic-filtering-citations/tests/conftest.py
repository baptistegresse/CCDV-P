import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from anthropic.types.beta import BetaMessage

FIXTURES = Path(__file__).parent / "fixtures"


def load_message(name: str, **overrides) -> BetaMessage:
    """Load a fixture as a real SDK object, optionally overriding top-level fields."""
    data = json.loads((FIXTURES / f"{name}.json").read_text())
    return BetaMessage.model_validate({**data, **overrides})


class FakeClient:
    """Stands in for anthropic.Anthropic: returns queued responses, records every request."""

    def __init__(self, responses: list[BetaMessage]):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs) -> BetaMessage:
        self.calls.append(kwargs)
        return self._responses.pop(0)


@pytest.fixture
def direct_message() -> BetaMessage:
    return load_message("direct_search")


@pytest.fixture
def error_message() -> BetaMessage:
    return load_message("search_error")
