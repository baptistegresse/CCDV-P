"""Turn Claude's content blocks into a readable answer with numbered sources.

Pure functions only: no API calls here, so everything is testable offline.

How citations arrive: Claude splits its answer into several `text` blocks.
A block that relies on a source carries a `citations` list; each entry of
type `web_search_result_location` has the source `url`, `title` and up to
150 characters of `cited_text`.
"""

from dataclasses import dataclass
from typing import Any, Iterable

WEB_CITATION_TYPE = "web_search_result_location"


@dataclass(frozen=True)
class Source:
    number: int
    url: str
    title: str
    quotes: tuple[str, ...]


@dataclass(frozen=True)
class Answer:
    text: str
    sources: tuple[Source, ...]


def _web_citations(block: Any) -> tuple[Any, ...]:
    citations = getattr(block, "citations", None) or ()
    return tuple(c for c in citations if c.type == WEB_CITATION_TYPE)


def _add_quote(sources: tuple[Source, ...], citation: Any) -> tuple[tuple[Source, ...], int]:
    """Return the sources with this citation recorded, plus the citation's footnote number."""
    for source in sources:
        if source.url == citation.url:
            updated = Source(source.number, source.url, source.title, (*source.quotes, citation.cited_text))
            return tuple(updated if s is source else s for s in sources), source.number

    number = len(sources) + 1
    new_source = Source(number, citation.url, citation.title or citation.url, (citation.cited_text,))
    return (*sources, new_source), number


def extract_answer(content: Iterable[Any]) -> Answer:
    """Join the text blocks and append [n] markers where Claude cited a source."""
    text_parts: tuple[str, ...] = ()
    sources: tuple[Source, ...] = ()

    for block in content:
        if block.type != "text":
            continue
        markers = ""
        for citation in _web_citations(block):
            sources, number = _add_quote(sources, citation)
            markers += f"[{number}]"
        text_parts = (*text_parts, block.text + markers)

    return Answer(text="".join(text_parts).strip(), sources=sources)


def search_queries(content: Iterable[Any]) -> tuple[str, ...]:
    """The queries Claude sent to web search, in order."""
    return tuple(
        block.input.get("query", "")
        for block in content
        if block.type == "server_tool_use" and block.name == "web_search"
    )


def search_errors(content: Iterable[Any]) -> tuple[str, ...]:
    """Error codes from failed searches.

    A failed search does NOT raise: the API returns HTTP 200 and the result
    block's `content` is a single error object instead of a list of results.
    """
    return tuple(
        block.content.error_code
        for block in content
        if block.type == "web_search_tool_result" and not isinstance(block.content, list)
    )


def format_answer(answer: Answer) -> str:
    if not answer.sources:
        return f"{answer.text}\n\nNo sources cited."

    lines = [answer.text, "", "Sources:"]
    for source in answer.sources:
        lines.append(f"  [{source.number}] {source.title}")
        lines.append(f"      {source.url}")
        lines.extend(f'      "{quote}"' for quote in source.quotes)
    return "\n".join(lines)
