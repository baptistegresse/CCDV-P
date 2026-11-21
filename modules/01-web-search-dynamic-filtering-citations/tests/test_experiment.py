import json

import pytest

from cited_search.experiment import (
    PLANS,
    Budget,
    Job,
    aggregate,
    build_jobs,
    estimate_plan_cost,
    format_report,
    main,
    summarize_run,
)
from cited_search.search import SearchMode, SearchResult, Usage
from tests.conftest import FakeClient, load_message


def _result(fixture: str) -> SearchResult:
    message = load_message(fixture)
    return SearchResult(message=message, content=tuple(message.content), usage=Usage(20_000, 800, 1), continuations=0)


def _row(model="claude-haiku-5-5", system="none", used_code=True, first_failed=True, format_error=True, cited=0):
    return dict(model=model, tool="web_search_20260318", system=system, q=0, rep=0, used_code=used_code,
                n_steps=2, first_failed=first_failed, format_error=format_error, input_tokens=30_000,
                output_tokens=900, cost=0.03, cited=cited, python_ok=None)


def test_quick_plan_is_cheap_enough_for_a_student():
    jobs = build_jobs(PLANS["quick"])

    assert len(jobs) == 14
    assert estimate_plan_cost(jobs) < 1.0


def test_full_plan_reproduces_the_90_runs():
    assert len(build_jobs(PLANS["full"])) == 90


def test_summarize_flags_a_first_step_that_treated_the_json_string_as_a_list():
    row = summarize_run(Job("claude-haiku-5-5", SearchMode.DYNAMIC, "none", 0, 1), _result("dynamic_two_steps"))

    assert row["used_code"] and row["n_steps"] == 2
    assert row["first_failed"] and row["format_error"]
    assert row["first_error"] == "TypeError: string indices must be integers"
    assert row["python_ok"] is True
    assert row["cost"] == pytest.approx(0.0124)


def test_summarize_a_direct_search_without_code():
    row = summarize_run(Job("claude-haiku-5-5", SearchMode.DYNAMIC, "none", 0, 0), _result("direct_search"))

    assert not row["used_code"] and not row["first_failed"]
    assert row["cited"] == 2
    assert row["python_ok"] is None


def test_budget_stops_new_runs_once_the_limit_is_reached():
    budget = Budget(stop_at=0.05)

    assert budget.can_start()
    budget.add(0.06)
    assert not budget.can_start()


def test_aggregate_counts_failures_among_runs_that_used_code():
    rows = [_row(), _row(), _row(used_code=False, first_failed=False, format_error=False, cited=3),
            _row(system="guide", first_failed=False, format_error=False)]

    groups = {(g["model"], g["system"]): g for g in aggregate(rows)}

    default = groups[("claude-haiku-5-5", "none")]
    assert (default["runs"], default["code_runs"], default["first_failed"], default["format_errors"]) == (3, 2, 2, 2)
    assert default["cited_direct"] == 1
    assert groups[("claude-haiku-5-5", "guide")]["first_failed"] == 0


def test_report_states_the_headline_figure():
    report = format_report([_row(), _row(), _row(first_failed=False, format_error=False)])

    assert "first code step failed in 2 of 3" in report


def test_run_refuses_to_spend_money_without_yes(capsys):
    client = FakeClient([])

    exit_code = main(["run", "--plan", "quick"], client=client)

    assert exit_code == 1
    assert client.calls == []
    assert "--yes" in capsys.readouterr().err


def test_run_writes_one_line_per_run(tmp_path):
    out = tmp_path / "runs.jsonl"
    client = FakeClient([load_message("dynamic_two_steps")] * 14)

    exit_code = main(["run", "--plan", "quick", "--yes", "--workers", "1", "--out", str(out)], client=client)

    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert exit_code == 0
    assert len(rows) == 14
    assert all(row["format_error"] for row in rows)


def test_analyze_prints_the_report(tmp_path, capsys):
    out = tmp_path / "runs.jsonl"
    out.write_text("\n".join(json.dumps(_row()) for _ in range(3)))

    assert main(["analyze", str(out)]) == 0
    assert "first code step failed in 3 of 3" in capsys.readouterr().out
