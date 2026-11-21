"""Open the "black box" of dynamic filtering.

With dynamic filtering, Claude writes Python that calls web search and picks
what to keep. Each step shows up in the response as:

- a `server_tool_use` block named `code_execution`: the code Claude wrote;
- `server_tool_use` / `web_search_tool_result` blocks whose `caller.tool_id`
  points to that step: the searches the code ran;
- a `code_execution_tool_result` block: what the code printed, which is what
  Claude reads. When the step called web search, the API returns its stdout
  ENCRYPTED (`encrypted_code_execution_result`); later steps that only work on
  the results print in clear text.
"""

from dataclasses import dataclass, replace
from typing import Any, Iterable

DEFAULT_MAX_OUTPUT_CHARS = 800


@dataclass(frozen=True)
class FilterStep:
    code: str
    queries: tuple[str, ...] = ()
    stdout: str | None = None
    stderr: str = ""
    return_code: int | None = None
    is_encrypted: bool = False


def _with_result(step: FilterStep, result: Any) -> FilterStep:
    kind = getattr(result, "type", "")
    if kind == "code_execution_result":
        return replace(step, stdout=result.stdout, stderr=result.stderr, return_code=result.return_code)
    if kind == "encrypted_code_execution_result":
        return replace(step, is_encrypted=True, stderr=result.stderr, return_code=result.return_code)
    return replace(step, stderr=f"error: {getattr(result, 'error_code', 'unknown')}")


def filtering_steps(content: Iterable[Any]) -> tuple[FilterStep, ...]:
    """The code execution steps of a dynamic-filtering turn, in order."""
    steps: dict[str, FilterStep] = {}
    for block in content:
        if block.type == "server_tool_use" and block.name == "code_execution":
            steps = {**steps, block.id: FilterStep(code=block.input.get("code", ""))}
        elif block.type == "server_tool_use" and block.name == "web_search":
            parent = getattr(getattr(block, "caller", None), "tool_id", None)
            if parent in steps:
                query = block.input.get("query", "")
                steps = {**steps, parent: replace(steps[parent], queries=(*steps[parent].queries, query))}
        elif block.type == "code_execution_tool_result" and block.tool_use_id in steps:
            steps = {**steps, block.tool_use_id: _with_result(steps[block.tool_use_id], block.content)}
    return tuple(steps.values())


def _format_output(step: FilterStep, max_chars: int) -> list[str]:
    if step.is_encrypted:
        return ["  output: encrypted by the API (this step called web_search)"]
    if step.stdout is None:
        return ["  output: none"]
    shown = step.stdout[:max_chars]
    lines = ["  output:", *(f"    {line}" for line in shown.splitlines())]
    hidden = len(step.stdout) - len(shown)
    if hidden > 0:
        lines.append(f"    ... ({hidden:,} more characters)")
    return lines


def format_filtering_steps(
    steps: tuple[FilterStep, ...], max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS
) -> str:
    if not steps:
        return "No filtering code in this answer (basic mode, or Claude didn't search)."

    lines: list[str] = []
    for number, step in enumerate(steps, 1):
        lines.append(f"── Filtering step {number} of {len(steps)} · code written by Claude ──")
        lines.extend(f"    {line}" for line in step.code.splitlines())
        lines.extend(f'  searched: "{query}"' for query in step.queries)
        if step.return_code not in (None, 0):
            last_error_line = (step.stderr.strip().splitlines() or [""])[-1]
            lines.append(f"  failed (return code {step.return_code}): {last_error_line}")
        lines.extend(_format_output(step, max_output_chars))
        lines.append("")
    return "\n".join(lines).rstrip()
