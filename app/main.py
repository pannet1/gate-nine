"""The one command.

    uv run python -m app.main

Runs the highest-numbered folder under test-cases/, or says plainly why it
cannot. Five steps, and the loop breaks at the first one that needs a human:

    1. find the highest-numbered run folder
    2. read its cases.yml — no cases.yml means nothing to run, so stop
    3. tidy: move loose recordings, fix drifted names, link into the run
    4. anything still missing is the human's — print the command and stop
    5. otherwise run every case in cases.yml, one at a time, in a visible browser

Nothing here decides what to test. cases.yml is the list, and the human's copy
of it wins.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from .config import settings
from .events import send_event
from .planner import find_latest_run
from .tidy import Workspace, read_cases, url_request

DEFAULT_RUNS_ROOT = Path("test-cases")
DEFAULT_RECORDINGS_DIR = Path("recordings")

RECORDING_SUFFIX = ".py"

# Exit codes, so a shell can tell the three outcomes apart.
EXIT_OK = 0        # every case ran and passed
EXIT_HANDOFF = 1   # tidy is done, something is waiting on the human
EXIT_CANNOT_RUN = 2  # no run, or no cases.yml — nothing was attempted


class CannotRun(Exception):
    """The loop cannot start. The message is the whole report."""


# --------------------------------------------------------------------------
# events
# --------------------------------------------------------------------------


def _log(run_id: str, action: str, details: dict[str, Any] | None = None) -> None:
    """POST one event, or do nothing when no endpoint is configured."""
    if not settings.events_url:
        return
    send_event(
        settings.events_url,
        settings.events_password,
        test_id=run_id,
        action=action,
        details={"run_folder": run_id, **(details or {})},
    )


# --------------------------------------------------------------------------
# steps 1 and 2 — is there anything to run
# --------------------------------------------------------------------------


def resolve_run(runs_root: Path, run_id: str | None = None) -> Path:
    """The run to work on: the named one, or the highest-numbered."""
    if run_id:
        run_dir = runs_root / run_id
        if not run_dir.is_dir():
            raise CannotRun(f"no run folder at {run_dir}")
        return run_dir
    run_dir = find_latest_run(runs_root)
    if run_dir is None:
        raise CannotRun(f"no numbered run folder under {runs_root}/")
    return run_dir


def read_run_cases(run_dir: Path) -> list[str]:
    """The cases to run, read from cases.yml.

    Absent or empty is fatal. Deriving a list from the filesystem instead would
    run whatever happened to be lying around, which is how the wrong case gets
    tested against the wrong brief.
    """
    cases = read_cases(run_dir)
    if cases is None:
        raise CannotRun(
            f"{run_dir / 'cases.yml'} is missing — there is no list of cases to run.\n"
            f"  Write it, or let the AI interpret the brief into it:\n"
            f"      cd /home/pannet1/gate-nine && uv run python -m app.tidy --run-id {run_dir.name}"
        )
    if not cases:
        raise CannotRun(f"{run_dir / 'cases.yml'} lists no cases.")
    return cases


# --------------------------------------------------------------------------
# steps 3 and 4 — tidy, then report what is left
# --------------------------------------------------------------------------


def prepare(ws: Workspace, run_dir: Path) -> dict[str, Any]:
    """Link the run's recordings into place. Returns tidy's report."""
    return ws.sync_run(run_dir.name, cases=read_run_cases(run_dir))


def handoff_lines(
    report: dict[str, Any], run_dir: Path, recordings_dir: Path
) -> list[str]:
    """The lines to print when the run cannot proceed without the human.

    URLs first — a recording cannot be made without knowing where to go. Then
    the recording command for any case that now has a URL.
    """
    lines: list[str] = []
    ask_url = report.get("ask_url_for", [])
    missing_py = report.get("missing_py", [])

    if ask_url:
        lines.append("")
        lines.append("These cases need a URL before anything can be recorded:")
        lines.extend(f"  {case}" for case in ask_url)
        lines.append("")
        lines.extend(f"  {url_request(recordings_dir, case)}" for case in ask_url)

    if missing_py:
        lines.append("")
        lines.append("These cases have no recording yet:")
        lines.extend(f"  {case}" for case in missing_py)
        recordable = [c for c in missing_py if (recordings_dir / c / "url.txt").is_file()]
        if recordable:
            lines.append("")
            lines.append("  record them with:")
            lines.extend(
                f"  uv run playwright codegen --load-storage={recordings_dir}/auth.json "
                f"-o {recordings_dir}/{case}/{case}{RECORDING_SUFFIX} "
                f'"$(cat {recordings_dir}/{case}/url.txt)"'
                for case in recordable
            )
        lines.append("")
        lines.append("  then re-run:")
        lines.append("      cd /home/pannet1/gate-nine && uv run python -m app.main")
    return lines


# --------------------------------------------------------------------------
# step 5 — run the cases
# --------------------------------------------------------------------------


def run_case(case: str, run_dir: Path) -> dict[str, Any]:
    """Run one recording in a visible browser, from its own folder.

    The recordings carry their own selectors and set headless=False; nothing is
    injected here. Working directory matters: storage_state is ../auth.json and
    the screenshot is a bare screenshot.png, both of which resolve only from the
    case folder. Following the run's symlink means the link is what gets
    exercised.
    """
    case_dir = run_dir / case
    recording = case_dir / f"{case}{RECORDING_SUFFIX}"
    if not recording.is_file():
        return {"case": case, "status": "missing", "detail": f"no {case}{RECORDING_SUFFIX}"}

    # Absolute, because cwd is about to change to the case folder — a relative
    # path would resolve against that and point at nothing.
    script = str(recording.resolve())
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, script],
        cwd=case_dir,
        capture_output=True,
        text=True,
    )
    # A traceback's last line is the error; the couple before it say where.
    tail = [line for line in (result.stderr or result.stdout or "").splitlines() if line.strip()]
    return {
        "case": case,
        "status": "passed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "seconds": round(time.monotonic() - started, 1),
        "detail": tail[-3:],
    }


def run_cases(
    cases: list[str],
    run_dir: Path,
    runner: Callable[[str, Path], dict[str, Any]] = run_case,
    delay: float | None = None,
) -> dict[str, Any]:
    """Every case, one at a time, in cases.yml order. Never parallel — the
    tenant is shared state.

    A failing case does not stop the others: each one launches its own browser,
    so one broken selector is one broken case, not a broken run. The loop
    continues until every case has either completed or been named as failed.

    STEP_DELAY holds between cases so a human can watch what was just entered
    before the next browser appears.
    """
    pause = settings.step_delay if delay is None else delay
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        if index and pause:
            time.sleep(pause)
        result = runner(case, run_dir)
        results.append(result)
        # One event per case as it happens, so a run that dies part-way still
        # left a record of everything before it.
        _log(
            run_dir.name,
            f"case_{result['status']}",
            {
                "case": case,
                "detail": result.get("detail", []),
                "seconds": result.get("seconds"),
            },
        )
    return {
        "action": "ran",
        "run_id": run_dir.name,
        "total": len(results),
        "passed": [r for r in results if r["status"] == "passed"],
        "failed": [r for r in results if r["status"] != "passed"],
        "results": results,
    }


def report_results(summary: dict[str, Any]) -> None:
    """Name the case, the step, and what failed. A number is not a report."""
    print()
    for result in summary["results"]:
        mark = "ok  " if result["status"] == "passed" else "FAIL"
        extra = f" ({result['seconds']}s)" if "seconds" in result else ""
        print(f"  {mark} {result['case']}{extra}")
        if result["status"] != "passed":
            for line in result.get("detail", []):
                print(f"       {line}")
    total = summary["total"]
    print()
    print(
        f"  {len(summary['passed'])}/{total} passed"
        + (f" — failed: {', '.join(r['case'] for r in summary['failed'])}" if summary["failed"] else "")
    )


# --------------------------------------------------------------------------
# the loop
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the highest test-case folder, or say why it cannot."
    )
    parser.add_argument("--run", dest="run_id", help="run id to use (default: the highest)")
    parser.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT))
    parser.add_argument("--recordings", dest="recordings_dir", default=str(DEFAULT_RECORDINGS_DIR))
    args = parser.parse_args(argv)

    runs_root = Path(args.runs_root)
    recordings_dir = Path(args.recordings_dir)
    ws = Workspace(runs_root=runs_root, recordings_dir=recordings_dir)

    try:
        run_dir = resolve_run(runs_root, args.run_id)
        report = prepare(ws, run_dir)
    except CannotRun as exc:
        print(f"cannot run: {exc}", file=sys.stderr)
        return EXIT_CANNOT_RUN

    print(f"run {run_dir.name} — {len(report.get('ask_url_for', []))} need a url")

    if report["missing_py"] or report["ask_url_for"]:
        for line in handoff_lines(report, run_dir, recordings_dir):
            print(line)
        return EXIT_HANDOFF

    cases = read_cases(run_dir) or []
    print(f"{len(cases)} case(s) recorded — running them now")
    _log(run_dir.name, "run_start", {"cases": len(cases)})

    summary = run_cases(cases, run_dir)
    report_results(summary)
    _log(
        run_dir.name,
        "run_result",
        {
            "total": summary["total"],
            "passed": len(summary["passed"]),
            "failed": [r["case"] for r in summary["failed"]],
        },
    )
    return EXIT_OK if not summary["failed"] else EXIT_HANDOFF


if __name__ == "__main__":
    raise SystemExit(main())