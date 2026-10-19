"""session.md — the working state a cold agent resumes from.

Rewritten in full every time. Never appended: history is not wanted.
"""

from datetime import datetime, timezone
from pathlib import Path

from .cases import RECORDING_SUFFIX

SESSION_FILENAME = "session.md"


def case_state(run_dir: Path, case: str) -> str:
    """A case is complete when its recording resolves inside the run folder."""
    return "complete" if (run_dir / case / f"{case}{RECORDING_SUFFIX}").exists() else "pending"


def render_session(
    run_dir: Path,
    brief: Path | None,
    cases: list[str],
    recordings_dir: Path,
    results: list[dict] | None = None,
) -> str:
    """The cases as a work list with state, and where the run currently is.

    ``results`` is what a playback pass has finished so far, in order. It is
    rewritten after every case, so a browser that dies halfway through still
    leaves a record of what ran and what did not.
    """
    states = {case: case_state(run_dir, case) for case in cases}
    ran = {r.get("case"): r for r in (results or [])}
    lines = [
        f"# Run {run_dir.name}",
        "",
        f"Brief: {brief.name if brief else '—'}",
        f"Recordings: `{recordings_dir}`",
        "",
        "## Cases",
        "",
    ]
    if not cases:
        lines.append("No cases yet.")
    for case in cases:
        result = ran.get(case)
        if result:
            marker = "x" if result.get("status") == "passed" else "!"
            note = result["status"]
        else:
            marker = "x" if states[case] == "complete" else " "
            note = states[case]
        lines.append(f"- [{marker}] `{case}` — {note}")

    lines += ["", "## Now", ""]
    if results:
        failed = [r["case"] for r in results if r.get("status") != "passed"]
        lines.append(f"Played back {len(results)} of {len(cases)} case(s).")
        if failed:
            lines.append(f"Failed: {', '.join(failed)}")
        remaining = [c for c in cases if c not in ran]
        lines.append(
            f"Next: `{remaining[0]}`" if remaining else "Every case in cases.yml was played."
        )
    else:
        pending = [c for c in cases if states[c] == "pending"]
        lines.append(
            f"Working on: `{pending[0]}`" if pending else "Every case has a recording."
        )
    lines.append(f"Updated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append("")
    return "\n".join(lines)


def write_session(
    run_dir: Path,
    brief: Path | None,
    cases: list[str],
    recordings_dir: Path,
    results: list[dict] | None = None,
) -> Path:
    session = run_dir / SESSION_FILENAME
    session.write_text(
        render_session(run_dir, brief, cases, recordings_dir, results), encoding="utf-8"
    )
    return session