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
    run_dir: Path, brief: Path | None, cases: list[str], recordings_dir: Path
) -> str:
    """The cases as a work list, and the one thing to do next.

    Deliberately not a record of outcomes. What a playback produced is reported
    on stdout and to the event stream; the PASS/FAIL verdict belongs to the
    human and never lands here.
    """
    states = {case: case_state(run_dir, case) for case in cases}
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
        marker = "x" if states[case] == "complete" else " "
        lines.append(f"- [{marker}] `{case}` — {states[case]}")

    pending = [c for c in cases if states[c] == "pending"]
    lines += ["", "## Now", ""]
    lines.append(f"Working on: `{pending[0]}`" if pending else "Every case has a recording.")
    lines.append(f"Updated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append("")
    return "\n".join(lines)


def write_session(
    run_dir: Path, brief: Path | None, cases: list[str], recordings_dir: Path
) -> Path:
    session = run_dir / SESSION_FILENAME
    session.write_text(render_session(run_dir, brief, cases, recordings_dir), encoding="utf-8")
    return session