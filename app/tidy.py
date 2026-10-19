"""Tidy the workspace: give loose recordings a case folder, link them into the
run, and report what state the run is in.

This is the mechanical part of the loop, done in code rather than by judgement
on every pass (index.html §4). It never interprets prose — the case names come
from what exists in ``recordings/``, or from ``--cases``.

    uv run python -m app.tidy
    uv run python -m app.tidy --dry-run

What it does, in order:

1. **Auth** — ``test-cases/auth.json`` points at the one real ``recordings/auth.json``.
2. **Tidy** — a loose ``recordings/<case>.py`` becomes ``recordings/<case>/<case>.py``,
   a recording whose name drifted from its folder is renamed to match, and its
   ``storage_state`` is pointed at the single system-wide ``auth.json``.
3. **Link** — each case with a recordings folder gets a symlink at
   ``test-cases/<run>/<case> -> ../../recordings/<case>``.
4. **Report** — every case is complete or not, and ``session.md`` is rewritten
   with that state.

Safety: a recording is never deleted or overwritten. A link is never replaced by
a copy. Every step is idempotent, so running it twice is a no-op.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from .planner import find_brief

RECORDING_SUFFIX = ".py"
SESSION_FILENAME = "session.md"
DEFAULT_RUNS_ROOT = Path("test-cases")
DEFAULT_RECORDINGS_DIR = Path("recordings")


def tidy_recordings(recordings_dir: Path, cases: list[str] | None = None) -> list[dict[str, Any]]:
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
        if cases is not None and case not in cases:
            continue
        case_dir = recordings_dir / case
        case_dir.mkdir(exist_ok=True)
        destination = case_dir / entry.name
        entry.replace(destination)
        moved.append({"case": case, "from": str(entry), "to": str(destination)})
    return moved


def normalise_recordings(recordings_dir: Path, cases: list[str] | None = None) -> list[dict[str, Any]]:
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
        if cases is not None and case_dir.name not in cases:
            continue
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


def link_system_auth(runs_root: Path, recordings_dir: Path) -> str:
    """Ensure test-cases/auth.json points at the one real file in recordings/.

    The real auth state lives at recordings/auth.json, where the human's
    recording command leaves it. test-cases/auth.json is a convenience link for
    anything that expects it there. Neither is committed — the gitignore
    pattern for auth.json covers both, so no dangling link enters the repo.
    """
    link = runs_root / "auth.json"
    expected = Path("..") / "recordings" / "auth.json"
    normalised = Path(os.path.normpath(expected))

    if link.is_symlink():
        if Path(os.path.normpath(os.readlink(link))) == normalised:
            return "already-linked"
        link.unlink()
    elif link.exists():
        return "skipped"

    if not (recordings_dir / "auth.json").exists():
        return "no-auth-file"

    link.symlink_to(expected)
    return "created"


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


def link_cases(run_dir: Path, recordings_dir: Path, cases: list[str]) -> dict[str, str]:
    """Link every named case into the run. Returns case -> what happened."""
    return {case: link_case(run_dir, recordings_dir, case) for case in cases}


AUTH_RELATIVE = "../auth.json"


def point_recording_at_auth(recordings_dir: Path, case: str) -> str:
    """Rewrite a recording's storage_state to the one system-wide auth.json.

    There is one auth file per system, at recordings/auth.json — the lazy
    human's codegen command puts it there. A case folder resolves to
    recordings/<case>/, so from there the file is ../auth.json. codegen
    writes a bare "auth.json", which resolves to nothing — fix it rather
    than copy the secret into every folder.
    """
    recording = recordings_dir / case / f"{case}{RECORDING_SUFFIX}"
    if not recording.is_file():
        return "no-recording"

    source = recording.read_text(encoding="utf-8")
    # Match any storage_state value, not just a bare "auth.json", so the path
    # converges no matter which form it was last written in.
    pattern = r"""(storage_state=)(["'])[^"']*(["'])"""
    if not re.search(pattern, source):
        return "nothing-to-rewrite"

    updated = re.sub(pattern, rf"\g<1>\g<2>{AUTH_RELATIVE}\g<3>", source)
    if updated == source:
        return "nothing-to-rewrite"
    recording.write_text(updated, encoding="utf-8")
    return "rewritten"


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


def cases_in_run(run_dir: Path, recordings_dir: Path) -> list[str]:
    """Case names for a run's session file: whatever is linked plus what exists."""
    linked = [entry.name for entry in sorted(run_dir.iterdir()) if entry.is_symlink()]
    available = case_folders(recordings_dir)
    return sorted(dict.fromkeys(linked + available))


def tidy_one_case(
    case: str,
    run_id: str,
    runs_root: Path = DEFAULT_RUNS_ROOT,
    recordings_dir: Path = DEFAULT_RECORDINGS_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Bring one case into one run, doing whatever that case still needs.

        uv run python -m app.tidy sales-invoice 001

    In order: give a loose recording its folder, fix a name that drifted,
    point the recording at the single auth file, symlink the case into the
    run, and rewrite session.md for the run.
    """
    run_dir = runs_root / run_id
    if not run_dir.is_dir():
        return {"action": "no-such-run", "run_id": run_id, "case": case}

    briefs = find_brief(run_dir)
    brief = briefs[0] if briefs else None
    names = [case]

    if dry_run:
        loose = recordings_dir / f"{case}.py"
        would_tidy = loose.is_file()
        return {
            "action": "would-prepare",
            "dry_run": True,
            "case": case,
            "run_id": run_id,
            "would_move": str(loose) if would_tidy else None,
            "would_move_to": str(recordings_dir / case / f"{case}.py") if would_tidy else None,
            "session": str(run_dir / SESSION_FILENAME),
        }

    tidied = tidy_recordings(recordings_dir, names)
    renamed = normalise_recordings(recordings_dir, names)
    auth_fixed = point_recording_at_auth(recordings_dir, case)
    linked = link_case(run_dir, recordings_dir, case)
    system_auth = link_system_auth(runs_root, recordings_dir)

    all_cases = cases_in_run(run_dir, recordings_dir)
    write_session(run_dir, brief, all_cases, recordings_dir)

    return {
        "action": "prepared",
        "dry_run": False,
        "case": case,
        "run_id": run_id,
        "brief": brief.name if brief else None,
        "tidied": tidied,
        "renamed": renamed,
        "auth_fixed": auth_fixed,
        "linked": linked,
        "system_auth": system_auth,
        "state": case_state(run_dir, case),
        "session": str(run_dir / SESSION_FILENAME),
    }


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
    auth_fixed = (
        {}
        if dry_run
        else {case: point_recording_at_auth(recordings_dir, case) for case in names}
    )
    links = {} if dry_run else link_cases(run_dir, recordings_dir, names)
    system_auth = "skipped" if dry_run else link_system_auth(runs_root, recordings_dir)
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
        "auth_fixed": auth_fixed,
        "linked": links,
        "system_auth": system_auth,
        "states": states,
        "pending": [case for case in names if states[case] == "pending"],
        "session": str(session),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tidy recordings, link them into a run, report state.",
        epilog=(
            "tidy.py <case> <run_id>   prepare one case into one run\n"
            "tidy.py                    prepare every case into the latest run"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("case", nargs="?", help="case name, e.g. sales-invoice")
    parser.add_argument("run_id", nargs="?", help="target run id, e.g. 001")
    parser.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT))
    parser.add_argument(
        "--recordings", dest="recordings_dir", default=str(DEFAULT_RECORDINGS_DIR)
    )
    parser.add_argument("--run-id", dest="run_id_opt", help="target a run (batch mode)")
    parser.add_argument("--cases", help="comma-separated case names, overrides discovery")
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would change, change nothing"
    )
    args = parser.parse_args()

    runs_root = Path(args.runs_root)
    recordings_dir = Path(args.recordings_dir)

    if args.case:
        report = tidy_one_case(
            case=args.case,
            run_id=args.run_id or args.run_id_opt,
            runs_root=runs_root,
            recordings_dir=recordings_dir,
            dry_run=args.dry_run,
        )
    else:
        names = (
            [n.strip() for n in args.cases.split(",") if n.strip()] if args.cases else None
        )
        report = prepare(
            runs_root=runs_root,
            recordings_dir=recordings_dir,
            run_id=args.run_id_opt or args.run_id,
            cases=names,
            dry_run=args.dry_run,
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
