"""Tidy the workspace: give loose recordings a case folder, link them into the
run, and report what state the run is in.

This is the mechanical part of the loop, done in code rather than by judgement
on every pass (index.html §4). It never interprets prose — the case names come
from what exists in ``recordings/``, or from ``--cases``.

    uv run python -m app.tidy
    uv run python -m app.tidy --dry-run

What it does, in order:

1. **Tidy** — a loose ``recordings/<case>.py`` becomes ``recordings/<case>/<case>.py``,
   and a recording whose name drifted from its folder is renamed to match.
2. **Link** — each case with a template folder gets a symlink at
   ``test-cases/<run>/<case> -> ../../recordings/<case>``.
3. **Report** — every case is complete or not, and ``session.md`` is rewritten
   with that state.

Safety: a recording is never deleted or overwritten. A link is never replaced by
a copy. Every step is idempotent, so running it twice is a no-op.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

RECORDING_SUFFIX = ".py"
SESSION_FILENAME = "session.md"
DEFAULT_RUNS_ROOT = Path("test-cases")
DEFAULT_RECORDINGS_DIR = Path("recordings")


def tidy_recordings(recordings_dir: Path) -> list[dict[str, Any]]:
    """Give every loose ``<case>.py`` in recordings_dir its own case folder.

    Returns one record per file moved. A file already inside a case folder is
    left alone — this only picks up recordings sitting flat in recordings_dir.
    """
    moved: list[dict[str, Any]] = []
    if not recordings_dir.is_dir():
        return moved

    for entry in sorted(recordings_dir.iterdir()):
        if not entry.is_file() or entry.suffix != RECORDING_SUFFIX:
            continue
        case = entry.stem
        case_dir = recordings_dir / case
        case_dir.mkdir(exist_ok=True)
        destination = case_dir / entry.name
        entry.replace(destination)
        moved.append({"case": case, "from": str(entry), "to": str(destination)})
    return moved


def normalise_recordings(recordings_dir: Path) -> list[dict[str, Any]]:
    """Make each case folder's recording match its folder name.

    A lazy or typo-prone human leaves ``<case>/<different>.py``. The link still
    works, but the completion check looks for ``<case>/<case>.py`` and would
    report the case pending forever. Rename it when there is exactly one
    candidate, so the intent is obvious.

    More than one recording in the folder is ambiguous — leave it and say so.
    """
    fixed: list[dict[str, Any]] = []
    if not recordings_dir.is_dir():
        return fixed

    for case_dir in sorted(e for e in recordings_dir.iterdir() if e.is_dir()):
        expected = case_dir / f"{case_dir.name}{RECORDING_SUFFIX}"
        if expected.exists():
            continue
        candidates = [
            entry for entry in sorted(case_dir.iterdir())
            if entry.is_file() and entry.suffix == RECORDING_SUFFIX
        ]
        if len(candidates) != 1:
            if candidates:
                fixed.append({
                    "case": case_dir.name,
                    "ambiguous": [c.name for c in candidates],
                })
            continue
        candidates[0].replace(expected)
        fixed.append({
            "case": case_dir.name,
            "from": candidates[0].name,
            "to": expected.name,
        })
    return fixed


def case_folders(recordings_dir: Path) -> list[str]:
    """Case names that have a folder in recordings_dir, sorted."""
    if not recordings_dir.is_dir():
        return []
    return sorted(
        entry.name for entry in recordings_dir.iterdir() if entry.is_dir()
    )


def link_case(run_dir: Path, recordings_dir: Path, case: str) -> str:
    """Point test-cases/<run>/<case> at recordings/<case>.

    Returns what happened: "created", "already-linked", "repaired" or "skipped".
    Never replaces a link with a copy, and never touches a real directory.
    """
    link = run_dir / case
    target = Path("..") / ".." / "recordings" / case
    expected = Path(os.path.normpath(target))

    if link.is_symlink():
        if Path(os.path.normpath(os.readlink(link))) == expected:
            return "already-linked"
        link.unlink()
        link.symlink_to(target, target_is_directory=True)
        return "repaired"

    if link.exists():
        # A real directory or file is sitting where the link belongs. Leave it.
        return "skipped"

    link.symlink_to(target, target_is_directory=True)
    return "created"


def link_cases(
    run_dir: Path,
    recordings_dir: Path,
    cases: list[str],
    auth_path: Path | None = None,
) -> dict[str, str]:
    """Link every named case into the run. Returns case -> what happened."""
    auth = auth_path if auth_path is not None else run_dir.parent / "auth.json"
    return {
        case: link_case(run_dir, recordings_dir, case) for case in cases
    } | {
        f"{case}/auth.json": link_auth(recordings_dir, case, auth) for case in cases
    }


def link_auth(recordings_dir: Path, case: str, auth_path: Path) -> str:
    """Point recordings/<case>/auth.json at the single system-wide auth.json.

    There is one auth.json per system, at test-cases/auth.json. A recording
    resolves ``storage_state="auth.json"`` from its own folder, so each case
    folder gets a link to it. The link is never committed — the target is
    gitignored, so a committed link would dangle on a fresh clone.
    """
    case_dir = recordings_dir / case
    if not case_dir.is_dir():
        return "no-case-folder"

    link = case_dir / "auth.json"
    expected = Path("..") / ".." / "test-cases" / "auth.json"
    normalised = Path(os.path.normpath(expected))

    if link.is_symlink():
        if Path(os.path.normpath(os.readlink(link))) == normalised:
            return "already-linked"
        link.unlink()
    elif link.exists():
        return "skipped"

    if not auth_path.exists():
        return "no-auth-file"

    link.symlink_to(expected)
    return "created"


def case_state(run_dir: Path, case: str) -> str:
    """A case is complete when its recording resolves inside the run folder."""
    return "complete" if (run_dir / case / f"{case}{RECORDING_SUFFIX}").exists() else "pending"


def render_session(
    run_dir: Path,
    brief: Path | None,
    cases: list[str],
    recordings_dir: Path,
) -> str:
    """Build the session file: the brief's cases as a work list with state."""
    states = {case: case_state(run_dir, case) for case in cases}
    pending = [case for case in cases if states[case] == "pending"]

    lines = [f"# Run {run_dir.name}", ""]
    lines.append(f"Brief: {brief.name if brief else '—'}")
    lines.append(f"Recordings: `{recordings_dir}`")
    lines.append("")

    if not cases:
        lines.append("No cases found. Record one, or pass --cases.")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Cases")
    lines.append("")
    width = max(len(case) for case in cases)
    for case in cases:
        marker = "x" if states[case] == "complete" else " "
        lines.append(f"- [{marker}] `{case}` — {states[case]}")
    lines.append("")

    lines.append("## Now")
    lines.append("")
    if pending:
        lines.append(f"Working on: `{pending[0]}`")
        url = run_dir / pending[0] / "url.txt"
        if not url.exists():
            lines.append("")
            lines.append(
                f"Blocked: `{url.relative_to(run_dir.parent)}` is missing — "
                "the URL is unknown. Ask the developer, do not infer it."
            )
    else:
        lines.append("Every case has a recording. The loop is done for this run.")
    lines.append("")

    return "\n".join(lines)


def write_session(run_dir: Path, brief: Path | None, cases: list[str], recordings_dir: Path) -> Path:
    """Rewrite session.md to the current state. Never appends."""
    session = run_dir / SESSION_FILENAME
    session.write_text(
        render_session(run_dir, brief, cases, recordings_dir), encoding="utf-8"
    )
    return session


def prepare(
    runs_root: Path = DEFAULT_RUNS_ROOT,
    recordings_dir: Path = DEFAULT_RECORDINGS_DIR,
    run_id: str | None = None,
    cases: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Tidy, link, report. Returns what happened."""
    from .planner import find_brief, find_latest_run

    if run_id is not None:
        run_dir = runs_root / run_id
        if not run_dir.is_dir():
            return {"action": "no-such-run", "run_id": run_id}
    else:
        run_dir = find_latest_run(runs_root)
        if run_dir is None:
            return {"action": "no-run", "root": str(runs_root)}

    briefs = find_brief(run_dir)
    brief = briefs[0] if briefs else None

    tidied = [] if dry_run else tidy_recordings(recordings_dir)
    renamed = [] if dry_run else normalise_recordings(recordings_dir)
    if dry_run:
        tidied = [
            {"case": e.stem, "from": str(e), "to": str(recordings_dir / e.stem / e.name)}
            for e in sorted(recordings_dir.glob(f"*{RECORDING_SUFFIX}"))
            if e.is_file()
        ]

    names = cases if cases is not None else case_folders(recordings_dir)
    links = {} if dry_run else link_cases(run_dir, recordings_dir, names)
    session = run_dir / SESSION_FILENAME
    if not dry_run:
        write_session(run_dir, brief, names, recordings_dir)

    states = {case: case_state(run_dir, case) for case in names}
    return {
        "action": "prepared",
        "dry_run": dry_run,
        "run_id": run_dir.name,
        "brief": brief.name if brief else None,
        "tidied": tidied,
        "renamed": renamed,
        "linked": links,
        "states": states,
        "pending": [case for case in names if states[case] == "pending"],
        "session": str(session),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tidy loose recordings, link them into the run, report state."
    )
    parser.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT))
    parser.add_argument(
        "--recordings", dest="recordings_dir", default=str(DEFAULT_RECORDINGS_DIR)
    )
    parser.add_argument("--run-id", help="target a specific run instead of the latest")
    parser.add_argument("--cases", help="comma-separated case names, overrides discovery")
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would change, change nothing"
    )
    args = parser.parse_args()

    names = [name.strip() for name in args.cases.split(",") if name.strip()] if args.cases else None
    report = prepare(
        runs_root=Path(args.runs_root),
        recordings_dir=Path(args.recordings_dir),
        run_id=args.run_id,
        cases=names,
        dry_run=args.dry_run,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()