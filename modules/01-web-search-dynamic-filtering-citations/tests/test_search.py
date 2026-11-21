import pytest

from cited_search.search import (
    SearchMode,
    TooManyContinuationsError,
    build_web_search_tool,
    run_search,
)
from tests.conftest import FakeClient, load_message


def test_dynamic_mode_uses_the_tool_version_with_dynamic_filtering():
    tool = build_web_search_tool(SearchMode.DYNAMIC)

    assert tool == {"type": "web_search_20260318", "name": "web_search"}


def test_basic_mode_uses_the_original_tool_version():
    tool = build_web_search_tool(SearchMode.BASIC)

    assert tool["type"] == "web_search_20250305"


def test_optional_limits_are_added_to_the_tool_definition():
    tool = build_web_search_tool(
        SearchMode.DYNAMIC, max_uses=3, allowed_domains=("docs.python.org",)
    )

    assert tool["max_uses"] == 3
    assert tool["allowed_domains"] == ["docs.python.org"]


def test_rejects_a_non_positive_max_uses():
    with pytest.raises(ValueError, match="max_uses"):
        build_web_search_tool(SearchMode.DYNAMIC, max_uses=0)


def test_single_request_when_claude_finishes_in_one_turn(direct_message):
    client = FakeClient([direct_message])

    result = run_search(client, "When was Claude Shannon born?", SearchMode.DYNAMIC)

    assert len(client.calls) == 1
    assert result.message is direct_message
    assert result.continuations == 0
    assert result.usage.web_search_requests == 1


def test_sends_the_tool_and_the_refusal_fallback(direct_message):
    client = FakeClient([direct_message])

    run_search(client, "When was Claude Shannon born?", SearchMode.DYNAMIC)

    request = client.calls[0]
    assert request["tools"] == [{"type": "web_search_20260318", "name": "web_search"}]
    assert request["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in request["betas"]


def test_resumes_a_paused_turn_by_sending_the_assistant_content_back(direct_message):
    paused = load_message("direct_search", stop_reason="pause_turn", id="msg_paused")
    client = FakeClient([paused, direct_message])

    result = run_search(client, "When was Claude Shannon born?", SearchMode.DYNAMIC)

    second_request = client.calls[1]["messages"]
    assert [m["role"] for m in second_request] == ["user", "assistant"]
    assert second_request[1]["content"] == paused.content
    assert result.continuations == 1


def test_keeps_every_paused_response_because_a_continuation_holds_only_new_content(
    direct_message, error_message
):
    first_pause = load_message("search_error", stop_reason="pause_turn")
    second_pause = load_message("search_error", stop_reason="pause_turn")
    client = FakeClient([first_pause, second_pause, direct_message])

    result = run_search(client, "question", SearchMode.DYNAMIC)

    third_request = client.calls[2]["messages"]
    assert third_request[1]["content"] == [*first_pause.content, *second_pause.content]
    assert result.content == (*first_pause.content, *second_pause.content, *direct_message.content)


def test_reuses_the_code_execution_container_when_resuming(direct_message):
    container = {"id": "container_abc", "expires_at": "2026-11-21T12:00:00Z"}
    paused = load_message("direct_search", stop_reason="pause_turn", container=container)
    client = FakeClient([paused, direct_message])

    run_search(client, "question", SearchMode.DYNAMIC)

    assert "container" not in client.calls[0]
    assert client.calls[1]["container"] == "container_abc"


def test_adds_up_usage_across_continuations(direct_message):
    paused = load_message("direct_search", stop_reason="pause_turn")
    client = FakeClient([paused, direct_message])

    result = run_search(client, "When was Claude Shannon born?", SearchMode.DYNAMIC)

    assert result.usage.input_tokens == 6039 * 2
    assert result.usage.web_search_requests == 2


def test_stops_after_the_continuation_limit():
    paused = load_message("direct_search", stop_reason="pause_turn")
    client = FakeClient([paused] * 3)

    with pytest.raises(TooManyContinuationsError):
        run_search(client, "question", SearchMode.DYNAMIC, max_continuations=2)


def test_rejects_an_empty_question():
    with pytest.raises(ValueError, match="question"):
        run_search(FakeClient([]), "   ", SearchMode.DYNAMIC)
