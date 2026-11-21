"""Command line: `cited-search ask "..."` and `cited-search compare "..."`."""

import argparse
import sys
from typing import Any

import anthropic

from cited_search.render import (
    extract_answer,
    format_answer,
    search_errors,
    search_queries,
    searched_pages,
)
from cited_search.models import DEFAULT_MODEL, MODELS, estimate_cost
from cited_search.search import SearchMode, SearchResult, TooManyContinuationsError, run_search

EXIT_OK = 0
EXIT_ERROR = 1
# Searches are most of the bill on Haiku ($0.01 each): cap them by default.
DEFAULT_MAX_USES = 5
MODES = {"basic": SearchMode.BASIC, "dynamic": SearchMode.DYNAMIC}


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", choices=list(MODELS), default=DEFAULT_MODEL, help=f"default: {DEFAULT_MODEL}")
    common.add_argument("--system", help="optional system prompt")
    common.add_argument(
        "--max-uses", type=int, default=DEFAULT_MAX_USES, help=f"cap searches per turn (default: {DEFAULT_MAX_USES})"
    )

    parser = argparse.ArgumentParser(
        prog="cited-search",
        description="Ask Claude a question it answers with live web search and cited sources.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    ask = commands.add_parser("ask", parents=[common], help="answer one question with citations")
    ask.add_argument("question")
    ask.add_argument(
        "--mode", choices=list(MODES), default="basic", help="basic = web_search_20250305, dynamic = web_search_20260318"
    )
    ask.add_argument("--domain", action="append", default=[], help="only search this domain (repeatable)")

    compare = commands.add_parser(
        "compare", parents=[common], help="run basic vs dynamic filtering and compare usage and cost"
    )
    compare.add_argument("question")
    return parser


def _ask(client: Any, args: argparse.Namespace) -> SearchResult:
    return run_search(
        client,
        args.question,
        MODES[args.mode],
        max_uses=args.max_uses,
        allowed_domains=tuple(args.domain),
        model=args.model,
        system=args.system,
    )


def _cost_line(result: SearchResult, model_id: str) -> str:
    cost = estimate_cost(result.usage, model_id)
    searches = result.usage.web_search_requests
    return (
        f"Estimated cost: ${cost.total:.4f} on {model_id} "
        f"(tokens ${cost.tokens:.4f} + {searches} search{'es' if searches != 1 else ''} ${cost.searches:.4f})"
    )


def _print_result(result: SearchResult, model_id: str) -> int:
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
    print(format_answer(extract_answer(result.content), searched_pages(result.content)))
    print()
    print(_cost_line(result, model_id))
    if result.message.stop_reason == "max_tokens":
        print("\nwarning: the answer was cut off (max_tokens reached)", file=sys.stderr)
    return EXIT_OK


def _print_comparison(basic: SearchResult, dynamic: SearchResult, model_id: str) -> None:
    rows = (("basic (20250305)", basic), ("dynamic (20260318)", dynamic))
    print(f"model: {model_id}")
    print(f"{'mode':<20}{'input tokens':>14}{'output tokens':>15}{'searches':>10}{'est. cost':>12}")
    for name, result in rows:
        usage = result.usage
        cost = estimate_cost(usage, model_id).total
        print(
            f"{name:<20}{usage.input_tokens:>14,}{usage.output_tokens:>15,}"
            f"{usage.web_search_requests:>10}{'$' + format(cost, '.4f'):>12}"
        )


def _run(client: Any, args: argparse.Namespace) -> int:
    if args.command == "ask":
        return _print_result(_ask(client, args), args.model)

    options = {"model": args.model, "system": args.system, "max_uses": args.max_uses}
    basic = run_search(client, args.question, SearchMode.BASIC, **options)
    dynamic = run_search(client, args.question, SearchMode.DYNAMIC, **options)
    _print_comparison(basic, dynamic, args.model)
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
