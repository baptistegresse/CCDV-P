"""Call Claude with the web search tool and handle the server-side loop.

Web search is a *server tool*: Anthropic runs the searches, you never execute
anything yourself. The only loop you own is `pause_turn`: when a long search
turn hits the server's iteration limit, the API stops with
`stop_reason == "pause_turn"`. To resume it:

- send every paused response back unchanged, in order (a continuation holds
  only NEW content, so dropping an earlier pause loses that work);
- send the same tools again;
- send the container id back, because dynamic filtering runs inside a code
  execution container;
- do not add a "continue" user message.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from cited_search.models import DEFAULT_MODEL, get_model

MAX_TOKENS = 16_000
DEFAULT_MAX_CONTINUATIONS = 5

# If a safety classifier declines the request, the API re-runs it on a
# fallback model chosen by refusal category, inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class SearchMode(Enum):
    # Every search result is loaded into Claude's context window.
    BASIC = "web_search_20250305"
    # Claude writes and runs code that filters results before they reach its
    # context window. Code execution is provisioned automatically: do NOT also
    # declare the code_execution tool.
    DYNAMIC = "web_search_20260318"


class TooManyContinuationsError(RuntimeError):
    pass


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    web_search_requests: int = 0

    def plus(self, message_usage: Any) -> "Usage":
        server = getattr(message_usage, "server_tool_use", None)
        searches = getattr(server, "web_search_requests", 0) or 0
        return Usage(
            input_tokens=self.input_tokens + message_usage.input_tokens,
            output_tokens=self.output_tokens + message_usage.output_tokens,
            web_search_requests=self.web_search_requests + searches,
        )


@dataclass(frozen=True)
class SearchResult:
    message: Any  # the last response (its stop_reason tells you how the turn ended)
    content: tuple[Any, ...]  # every block of the turn, across all continuations
    usage: Usage
    continuations: int


def build_web_search_tool(
    mode: SearchMode,
    max_uses: int | None = None,
    allowed_domains: tuple[str, ...] = (),
) -> dict:
    if max_uses is not None and max_uses < 1:
        raise ValueError("max_uses must be at least 1")

    tool: dict = {"type": mode.value, "name": "web_search"}
    if max_uses is not None:
        tool = {**tool, "max_uses": max_uses}
    if allowed_domains:
        tool = {**tool, "allowed_domains": list(allowed_domains)}
    return tool


def run_search(
    client: Any,
    question: str,
    mode: SearchMode,
    max_uses: int | None = None,
    allowed_domains: tuple[str, ...] = (),
    max_continuations: int = DEFAULT_MAX_CONTINUATIONS,
    model: str = DEFAULT_MODEL,
    system: str | None = None,
) -> SearchResult:
    """Ask `question` with web search enabled and return Claude's final message."""
    if not question.strip():
        raise ValueError("question must not be empty")

    model_info = get_model(model)
    tool = build_web_search_tool(mode, max_uses, allowed_domains)
    optional_args: dict = {"system": system} if system else {}
    if model_info.supports_fallbacks:
        optional_args = {**optional_args, "betas": [FALLBACK_BETA], "fallbacks": "default"}
    user_turn = {"role": "user", "content": question}
    turn_content: tuple[Any, ...] = ()
    container_id: str | None = None
    usage = Usage()

    for continuation in range(max_continuations + 1):
        messages = [user_turn]
        if turn_content:
            messages = [user_turn, {"role": "assistant", "content": list(turn_content)}]
        resume_args = {"container": container_id} if container_id else {}

        message = client.beta.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            messages=messages,
            tools=[tool],
            **optional_args,
            **resume_args,
        )
        usage = usage.plus(message.usage)
        turn_content = (*turn_content, *message.content)

        if message.stop_reason != "pause_turn":
            return SearchResult(
                message=message, content=turn_content, usage=usage, continuations=continuation
            )

        if message.container:
            container_id = message.container.id

    raise TooManyContinuationsError(
        f"Claude was still searching after {max_continuations} continuations"
    )
