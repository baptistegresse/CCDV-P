"""Command line: `cited-search ask "..."` and `cited-search compare "..."`."""

import argparse
import sys
from typing import Any

import anthropic

from cited_search.render import extract_answer, format_answer, search_errors, search_queries
from cited_search.search import SearchMode, SearchResult, TooManyContinuationsError, run_search

EXIT_OK = 0
EXIT_ERROR = 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cited-search",
        description="Ask Claude a question it answers with live web search and cited sources.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    ask = commands.add_parser("ask", help="answer one question with citations")
    ask.add_argument("question")
    ask.add_argument("--basic", action="store_true", help="use web_search_20250305 (no dynamic filtering)")
    ask.add_argument("--max-uses", type=int, help="cap the number of searches in the turn")
    ask.add_argument("--domain", action="append", default=[], help="only search this domain (repeatable)")

    compare = commands.add_parser("compare", help="run basic vs dynamic filtering and compare token usage")
    compare.add_argument("question")
    return parser


def _ask(client: Any, args: argparse.Namespace) -> SearchResult:
    mode = SearchMode.BASIC if args.basic else SearchMode.DYNAMIC
    return run_search(
        client,
        args.question,
        mode,
        max_uses=args.max_uses,
        allowed_domains=tuple(args.domain),
    )


def _print_result(result: SearchResult) -> int:
    if result.message.stop_reason == "refusal":
        details = result.message.stop_details
        explanation = details.explanation if details else "no details"
        print(f"Claude declined this request: {explanation}", file=sys.stderr)
        return EXIT_ERROR

    for code in search_errors(result.content):
        print(f"warning: a web search failed ({code})", file=sys.stderr)

    queries = search_queries(result.content)
    print("Searched for: " + (", ".join(f'"{q}"' for q in queries) or "nothing (answered directly)"))
    print()
    print(format_answer(extract_answer(result.content)))
    if result.message.stop_reason == "max_tokens":
        print("\nwarning: the answer was cut off (max_tokens reached)", file=sys.stderr)
    return EXIT_OK


def _print_comparison(basic: SearchResult, dynamic: SearchResult) -> None:
    rows = (("basic (20250305)", basic.usage), ("dynamic (20260318)", dynamic.usage))
    print(f"{'mode':<20}{'input tokens':>14}{'output tokens':>15}{'searches':>10}")
    for name, usage in rows:
        print(
            f"{name:<20}{usage.input_tokens:>14,}{usage.output_tokens:>15,}{usage.web_search_requests:>10}"
        )


def _run(client: Any, args: argparse.Namespace) -> int:
    if args.command == "ask":
        return _print_result(_ask(client, args))

    basic = run_search(client, args.question, SearchMode.BASIC)
    dynamic = run_search(client, args.question, SearchMode.DYNAMIC)
    _print_comparison(basic, dynamic)
    return EXIT_OK


def main(argv: list[str] | None = None, client: Any = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(client or anthropic.Anthropic(), args)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
    except TooManyContinuationsError as error:
        print(f"error: {error}", file=sys.stderr)
    except anthropic.AuthenticationError:
        print("error: no valid credentials. Set ANTHROPIC_API_KEY (see .env.example).", file=sys.stderr)
    except anthropic.RateLimitError:
        print("error: Rate limited by the API. Wait a moment and retry.", file=sys.stderr)
    except anthropic.APIStatusError as error:
        print(f"error: the API returned {error.status_code}: {error.message}", file=sys.stderr)
    except anthropic.APIConnectionError:
        print("error: could not reach the Anthropic API. Check your network.", file=sys.stderr)
    return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
