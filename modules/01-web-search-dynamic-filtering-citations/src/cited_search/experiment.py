"""Reproduce the dynamic-filtering experiment: does Claude's first code step fail?

    uv run cited-search-experiment run --plan quick --yes     # 14 runs, about $0.40
    uv run cited-search-experiment run --plan full --yes      # 90 runs, about $8
    uv run cited-search-experiment analyze results/<file>.jsonl

Each run writes one JSON line: a summary only. Raw API responses are never
saved, because their encrypted fields carry your organization's id.
"""

import argparse
import json
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any

import anthropic

from cited_search.filtering import filtering_steps
from cited_search.models import estimate_cost
from cited_search.render import extract_answer, search_errors
from cited_search.search import SearchMode, SearchResult, run_search

QUESTIONS = (
    "What new Claude models did Anthropic release in 2026? Answer in 3 sentences.",
    "What is the latest stable Python version and when was it released? Two sentences.",
    "Compare the current hourly on-demand price of one NVIDIA H100 GPU on AWS, Google Cloud and Azure.",
    "What are the main new features of the latest Django release?",
    "Who won the 2026 FIFA World Cup final and what was the score?",
    "What does the CSA W59 standard cover, and what is its latest edition?",
    "What are the headline features of the latest stable Rust release?",
)
PYTHON_QUESTION = 1
PYTHON_EXPECTED = "3.15"  # update when a newer Python ships
GUIDE = (
    "When you filter web search results with code: web_search returns a JSON string, so parse it with "
    "json.loads first. Then keep only the results whose title or content mention the key terms of the "
    "question, prefer the most recent ones (check page_age and the dates in the content), and print the "
    "passages around those terms. Never truncate the raw results before filtering them."
)
GENERIC = "You are a helpful research assistant. Answer accurately and concisely."
SYSTEM_PROMPTS = {"none": None, "guide": GUIDE, "generic": GENERIC}
FORMAT_ERRORS = ("'str' object has no attribute", "string indices must be integers")
MAX_USES = 5
# Rough cost per run measured in November 2026, used only to warn before spending.
EST_COST_PER_RUN = {"claude-haiku-5-5": 0.03, "claude-sonnet-5-5": 0.12,
                    "claude-opus-5-5": 0.20, "claude-fable-5-2": 0.60}

ALL_Q = tuple(range(len(QUESTIONS)))
FEW_Q = (0, 1, 2)
H, S, O, F = "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2"
D18, D09 = SearchMode.DYNAMIC, SearchMode.DYNAMIC_20260209
# (model, tool version, system prompt, repetitions, question indexes)
PLANS = {
    "quick": ((H, D18, "none", 1, ALL_Q), (H, D18, "guide", 1, ALL_Q)),
    "full": (
        (H, D18, "none", 3, ALL_Q), (S, D18, "none", 2, ALL_Q), (H, D18, "guide", 2, ALL_Q),
        (S, D18, "guide", 1, ALL_Q), (O, D18, "none", 1, ALL_Q), (H, D09, "none", 1, ALL_Q),
        (S, D09, "none", 1, ALL_Q), (H, D18, "generic", 1, ALL_Q), (O, D18, "guide", 1, FEW_Q),
        (F, D18, "none", 1, FEW_Q),
    ),
}


@dataclass(frozen=True)
class Job:
    model: str
    tool: SearchMode
    system: str
    rep: int
    q: int


class Budget:
    """Stops new runs once the estimated spend reaches `stop_at` (runs in flight still finish)."""

    def __init__(self, stop_at: float):
        self.stop_at, self.spent, self._lock = stop_at, 0.0, threading.Lock()

    def can_start(self) -> bool:
        with self._lock:
            return self.spent < self.stop_at

    def add(self, cost: float) -> None:
        with self._lock:
            self.spent += cost


def build_jobs(plan: tuple) -> tuple[Job, ...]:
    return tuple(Job(m, t, s, rep, q) for (m, t, s, reps, qs) in plan for rep in range(reps) for q in qs)


def estimate_plan_cost(jobs: tuple[Job, ...]) -> float:
    return sum(EST_COST_PER_RUN[job.model] for job in jobs)


def summarize_run(job: Job, result: SearchResult) -> dict:
    steps = filtering_steps(result.content)
    first = steps[0] if steps else None
    first_failed = bool(first and first.return_code not in (0, None))
    answer = extract_answer(result.content)
    return dict(
        model=job.model, tool=job.tool.value, system=job.system, rep=job.rep, q=job.q,
        stop=result.message.stop_reason, used_code=bool(steps), n_steps=len(steps),
        first_failed=first_failed,
        format_error=first_failed and any(marker in first.stderr for marker in FORMAT_ERRORS),
        first_error=(first.stderr.strip().splitlines() or [""])[-1][:160] if first else "",
        first_code=first.code[:500] if first else "",
        input_tokens=result.usage.input_tokens, output_tokens=result.usage.output_tokens,
        searches=result.usage.web_search_requests, search_errors=list(search_errors(result.content)),
        cost=round(estimate_cost(result.usage, job.model).total, 4), cited=len(answer.sources),
        python_ok=(PYTHON_EXPECTED in answer.text) if job.q == PYTHON_QUESTION else None,
    )


def _run_job(client: Any, job: Job, budget: Budget, out: Path, lock: threading.Lock) -> None:
    if not budget.can_start():
        return
    try:
        result = run_search(client, QUESTIONS[job.q], job.tool, max_uses=MAX_USES,
                            model=job.model, system=SYSTEM_PROMPTS[job.system])
        row = summarize_run(job, result)
    except anthropic.APIError as error:
        row = dict(model=job.model, tool=job.tool.value, system=job.system, rep=job.rep, q=job.q,
                   error=f"{type(error).__name__}: {error}"[:300], cost=0.0)
    budget.add(row["cost"])
    with lock:
        with out.open("a") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[${budget.spent:.2f}] {job.model} {job.tool.value} {job.system} q{job.q} "
              f"first_failed={row.get('first_failed')} {row.get('error', '')}", flush=True)


def aggregate(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        if "error" not in row:
            groups[(row["model"], row["tool"], row["system"])].append(row)
    summary = []
    for (model, tool, system), runs in sorted(groups.items()):
        code = [r for r in runs if r["used_code"]]
        direct = [r for r in runs if not r["used_code"]]
        summary.append(dict(
            model=model, tool=tool, system=system, runs=len(runs), code_runs=len(code),
            first_failed=sum(r["first_failed"] for r in code), format_errors=sum(r["format_error"] for r in code),
            steps=mean(r["n_steps"] for r in code) if code else 0.0,
            input_tokens=mean(r["input_tokens"] for r in runs), cost=mean(r["cost"] for r in runs),
            cited_code=sum(1 for r in code if r["cited"]), cited_direct=sum(1 for r in direct if r["cited"]),
            direct_runs=len(direct),
        ))
    return summary


def format_report(rows: list[dict]) -> str:
    ok = [r for r in rows if "error" not in r]
    default_code = [r for r in ok if r["system"] != "guide" and r["used_code"]]
    lines = [
        f"{len(ok)} runs, ${sum(r['cost'] for r in ok):.2f} estimated, {len(rows) - len(ok)} API errors",
        f"Without guidance, the first code step failed in {sum(r['first_failed'] for r in default_code)} "
        f"of {len(default_code)} runs that used code "
        f"({sum(r['format_error'] for r in default_code)} because the JSON string was treated as a list).",
        "",
        f"{'model':<18}{'tool':<10}{'system':<9}{'runs':>5}{'1st fail':>10}{'format':>8}"
        f"{'steps':>7}{'in tok':>9}{'$/run':>8}{'cited code/direct':>19}",
    ]
    for g in aggregate(rows):
        lines.append(
            f"{g['model']:<18}{g['tool'][-8:]:<10}{g['system']:<9}{g['runs']:>5}"
            f"{g['first_failed']:>5} / {g['code_runs']:<2}{g['format_errors']:>8}{g['steps']:>7.1f}"
            f"{g['input_tokens']:>9,.0f}{g['cost']:>8.3f}"
            f"{g['cited_code']:>9} / {g['code_runs']:<2} {g['cited_direct']:>2} / {g['direct_runs']:<2}"
        )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cited-search-experiment", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run a plan against the real API (costs money)")
    run.add_argument("--plan", choices=list(PLANS), default="quick")
    run.add_argument("--yes", action="store_true", help="confirm you accept the estimated cost")
    run.add_argument("--budget", type=float, default=None, help="stop starting runs past this spend (USD)")
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("--out", default=f"results/{date.today().isoformat()}-runs.jsonl")
    analyze = commands.add_parser("analyze", help="summarize a results file")
    analyze.add_argument("path")
    return parser


def main(argv: list[str] | None = None, client: Any = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "analyze":
        rows = [json.loads(line) for line in Path(args.path).read_text().splitlines() if line.strip()]
        print(format_report(rows))
        return 0

    jobs = build_jobs(PLANS[args.plan])
    estimate = estimate_plan_cost(jobs)
    if not args.yes:
        print(f"The '{args.plan}' plan makes {len(jobs)} real API calls, about ${estimate:.2f}. "
              "Rerun with --yes to accept.", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    budget, lock = Budget(args.budget if args.budget is not None else estimate * 1.3), threading.Lock()
    with ThreadPoolExecutor(max(1, args.workers)) as pool:
        for job in jobs:
            pool.submit(_run_job, client or anthropic.Anthropic(), job, budget, out, lock)
    print(f"\nDone: ${budget.spent:.2f} estimated. Results in {out}\n")
    print(format_report([json.loads(line) for line in out.read_text().splitlines() if line.strip()]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
