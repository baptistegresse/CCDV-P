import httpx2
import anthropic

from cited_search.cli import main
from tests.conftest import FakeClient, load_message


class FailingClient(FakeClient):
    def __init__(self, error: Exception):
        super().__init__([])
        self._error = error

    def _create(self, **kwargs):
        raise self._error


def _api_error(cls, status: int):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status, request=request)
    return cls("boom", response=response, body=None)


def test_ask_prints_the_answer_with_numbered_sources(direct_message, capsys):
    exit_code = main(["ask", "When was Claude Shannon born?"], client=FakeClient([direct_message]))

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Petoskey, Michigan[1]" in output
    assert "[2] Claude Shannon | Britannica" in output
    assert "claude shannon birth date" in output


def test_ask_shows_searched_pages_when_dynamic_answer_has_no_citations(capsys):
    main(["ask", "question"], client=FakeClient([load_message("dynamic_search")]))

    output = capsys.readouterr().out
    assert "No inline citations" in output
    assert "PEP 745" in output


def test_ask_prints_an_estimated_cost(direct_message, capsys):
    main(["ask", "--model", "claude-haiku-5-5", "question"], client=FakeClient([direct_message]))

    output = capsys.readouterr().out
    assert "Estimated cost: $0.0111" in output  # 6,039 in + 931 out on Haiku + 1 search
    assert "claude-haiku-5-5" in output


def test_ask_passes_model_and_system_prompt(direct_message):
    client = FakeClient([direct_message])

    main(["ask", "--model", "claude-sonnet-5-5", "--system", "Cite sources.", "question"], client=client)

    assert client.calls[0]["model"] == "claude-sonnet-5-5"
    assert client.calls[0]["system"] == "Cite sources."


def test_compare_prints_a_cost_column(direct_message, error_message, capsys):
    main(["compare", "--model", "claude-haiku-5-5", "question"], client=FakeClient([error_message, direct_message]))

    assert "est. cost" in capsys.readouterr().out


def test_defaults_protect_the_budget_haiku_basic_mode_and_a_search_cap(direct_message):
    client = FakeClient([direct_message])

    main(["ask", "question"], client=client)

    request = client.calls[0]
    assert request["model"] == "claude-haiku-5-5"
    assert request["tools"][0]["type"] == "web_search_20250305"
    assert request["tools"][0]["max_uses"] == 5


def test_mode_flag_switches_to_dynamic_filtering(direct_message):
    client = FakeClient([direct_message])

    main(["ask", "--mode", "dynamic", "question"], client=client)

    assert client.calls[0]["tools"][0]["type"] == "web_search_20260318"


def test_compare_applies_the_same_search_cap_to_both_modes(direct_message, error_message):
    client = FakeClient([error_message, direct_message])

    main(["compare", "--max-uses", "2", "question"], client=client)

    assert [c["tools"][0]["max_uses"] for c in client.calls] == [2, 2]


def test_ask_passes_domain_and_max_uses_limits(direct_message):
    client = FakeClient([direct_message])

    main(["ask", "--max-uses", "2", "--domain", "python.org", "question"], client=client)

    tool = client.calls[0]["tools"][0]
    assert tool["max_uses"] == 2
    assert tool["allowed_domains"] == ["python.org"]


def test_ask_warns_about_failed_searches(error_message, capsys):
    main(["ask", "question"], client=FakeClient([error_message]))

    assert "max_uses_exceeded" in capsys.readouterr().err


def test_compare_runs_both_modes_and_prints_the_token_difference(direct_message, error_message, capsys):
    client = FakeClient([error_message, direct_message])

    exit_code = main(["compare", "question"], client=client)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert [c["tools"][0]["type"] for c in client.calls] == ["web_search_20250305", "web_search_20260318"]
    assert "120" in output and "6,039" in output


def test_refusal_is_reported_instead_of_an_empty_answer(capsys):
    refused = load_message(
        "search_error",
        stop_reason="refusal",
        stop_details={"type": "refusal", "category": None, "explanation": "declined"},
    )

    exit_code = main(["ask", "question"], client=FakeClient([refused]))

    assert exit_code == 1
    assert "declined" in capsys.readouterr().err


def test_missing_credentials_give_a_helpful_message(capsys):
    client = FailingClient(_api_error(anthropic.AuthenticationError, 401))

    exit_code = main(["ask", "question"], client=client)

    assert exit_code == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_rate_limit_is_reported(capsys):
    client = FailingClient(_api_error(anthropic.RateLimitError, 429))

    assert main(["ask", "question"], client=client) == 1
    assert "Rate limited" in capsys.readouterr().err
