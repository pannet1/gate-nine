"""Bring recordings into a run: move loose files into case folders, link them,
and report only what genuinely needs a human.

    uv run python -m app.tidy sales-invoice 001   one case into one run
    uv run python -m app.tidy                      every case into the latest run
    uv run python -m app.tidy ... --dry-run       report without moving anything

The rule is deliberately small:

    a case that has a recording  -> linked, silently
    a case that has none         -> the only thing worth complaining about
    a linked case with no url.txt -> what to ask the human for next

Nothing is inferred from prose. The case list is read from cases.yml when it
exists, and written from what is on disk only when it does not.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .planner import find_brief, find_latest_run

RECORDING_SUFFIX = ".py"
SESSION_FILENAME = "session.md"
CASES_FILENAME = "cases.yml"
DEFAULT_RUNS_ROOT = Path("test-cases")
DEFAULT_RECORDINGS_DIR = Path("recordings")

# Where the one system-wide auth.json lives, relative to a case folder.
AUTH_RELATIVE = "../auth.json"


# --------------------------------------------------------------------------
# case list
# --------------------------------------------------------------------------


def read_cases(run_dir: Path) -> list[str] | None:
    """Read cases.yml if present — the human may have corrected it.

    Returns None when absent or malformed. Never raises: a bad file is a
    discrepancy to report, not a crash.
    """
    path = run_dir / CASES_FILENAME
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    if isinstance(data, list) and all(isinstance(item, str) for item in data):
        return data
    if isinstance(data, dict) and isinstance(data.get("cases"), list):
        return [c for c in data["cases"] if isinstance(c, str)]
    return None


def write_cases(run_dir: Path, cases: list[str]) -> Path:
    """Record the interpreted case list so the human can correct it.

    Written only when absent — an existing cases.yml is the human's.
    """
    path = run_dir / CASES_FILENAME
    if path.exists():
        return path
    header = (
        "# Cases interpreted from the brief.\n"
        "# Correct this freely — the run reads this file in preference to\n"
        "# anything inferred, and never overwrites it.\n"
    )
    path.write_text(
        header + yaml.safe_dump({"cases": list(cases)}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def case_folders(recordings_dir: Path) -> list[str]:
    """Case names with a folder in recordings_dir, sorted."""
    if not recordings_dir.is_dir():
        return []
    return sorted(e.name for e in recordings_dir.iterdir() if e.is_dir())


def discover_cases(recordings_dir: Path) -> list[str]:
    """Every case on disk — folders, and recordings the human left flat.

    A lazy human records straight into recordings/, so a loose <case>.py is a
    case waiting to be tidied and must be discovered too.
    """
    if not recordings_dir.is_dir():
        return []
    names = set(case_folders(recordings_dir))
    names |= {
        e.stem for e in recordings_dir.iterdir()
        if e.is_file() and e.suffix == RECORDING_SUFFIX
    }
    return sorted(names)


# --------------------------------------------------------------------------
# the whole rule
# --------------------------------------------------------------------------


def classify(recordings_dir: Path, cases: list[str]) -> dict[str, list[str]]:
    """Split the cases three ways: linkable, missing a .py, missing a URL."""
    linked: list[str] = []
    missing_py: list[str] = []
    ask_url: list[str] = []
    for case in cases:
        case_dir = recordings_dir / case
        # Any .py in the case folder counts as recorded — even a drifted
        # filename, which normalise_recordings will then rename. Otherwise a
        # typo would be reported as "no recording at all" instead of fixed.
        any_py = case_dir.is_dir() and any(
            e.suffix == RECORDING_SUFFIX for e in case_dir.iterdir() if e.is_file()
        )
        if any_py or (recordings_dir / f"{case}{RECORDING_SUFFIX}").exists():
            linked.append(case)
            if not (case_dir / "url.txt").exists():
                ask_url.append(case)
        else:
            missing_py.append(case)
    return {"linked": linked, "missing_py": missing_py, "ask_url": ask_url}


def url_request(recordings_dir: Path, case: str) -> str:
    """The line to hand over when a case needs its URL."""
    return f"echo '<url>' > {recordings_dir}/{case}/url.txt"


# --------------------------------------------------------------------------
# tidying
# --------------------------------------------------------------------------


def tidy_recordings(recordings_dir: Path, cases: list[str] | None = None) -> list[str]:
    """Give every loose ``<case>.py`` its own case folder.

    Only picks up recordings sitting flat in recordings_dir; one already in a
    case folder is left alone.
    """
    moved: list[str] = []
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
        entry.replace(case_dir / entry.name)
        moved.append(case)
    return moved


def normalise_recordings(recordings_dir: Path, cases: list[str] | None = None) -> list[str]:
    """Make each case folder's recording match its folder name.

    ``effort-hours/effort-hour.py`` links fine but the completion check looks
    for ``effort-hours/effort-hours.py``. Rename it when there is exactly one
    candidate; two recordings are ambiguous, so leave them and report.
    """
    fixed: list[str] = []
    if not recordings_dir.is_dir():
        return fixed
    for case_dir in sorted(e for e in recordings_dir.iterdir() if e.is_dir()):
        if cases is not None and case_dir.name not in cases:
            continue
        expected = case_dir / f"{case_dir.name}{RECORDING_SUFFIX}"
        if expected.exists():
            continue
        candidates = [
            e for e in sorted(case_dir.iterdir())
            if e.is_file() and e.suffix == RECORDING_SUFFIX
        ]
        if len(candidates) == 1:
            candidates[0].replace(expected)
            fixed.append(case_dir.name)
        elif candidates:
            fixed.append(f"{case_dir.name} (ambiguous: {', '.join(c.name for c in candidates)})")
    return fixed


def point_recording_at_auth(recordings_dir: Path, case: str) -> str:
    """Rewrite a recording's storage_state to the one system-wide auth.json.

    The real file is recordings/auth.json. A case folder resolves to
    recordings/<case>/, so from there it is ../auth.json. codegen writes a bare
    "auth.json", which resolves to nothing.
    """
    recording = recordings_dir / case / f"{case}{RECORDING_SUFFIX}"
    if not recording.is_file():
        return "no-recording"
    source = recording.read_text(encoding="utf-8")
    pattern = r"""(storage_state=)(["'])[^"']*(["'])"""
    if not re.search(pattern, source):
        return "nothing-to-rewrite"
    updated = re.sub(pattern, rf"\g<1>\g<2>{AUTH_RELATIVE}\g<3>", source)
    if updated == source:
        return "nothing-to-rewrite"
    recording.write_text(updated, encoding="utf-8")
    return "rewritten"


# --------------------------------------------------------------------------
# linking
# --------------------------------------------------------------------------


def link_case(run_dir: Path, recordings_dir: Path, case: str) -> str:
    """Point test-cases/<run>/<case> at recordings/<case>.

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
        return "skipped"
    link.symlink_to(target, target_is_directory=True)
    return "created"


def link_cases(run_dir: Path, recordings_dir: Path, cases: list[str]) -> dict[str, str]:
    return {case: link_case(run_dir, recordings_dir, case) for case in cases}


def link_system_auth(runs_root: Path, recordings_dir: Path) -> str:
    """Ensure test-cases/auth.json points at the one real file in recordings/."""
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


# --------------------------------------------------------------------------
# session
# --------------------------------------------------------------------------


def case_state(run_dir: Path, case: str) -> str:
    """A case is complete when its recording resolves inside the run folder."""
    return "complete" if (run_dir / case / f"{case}{RECORDING_SUFFIX}").exists() else "pending"


def render_session(
    run_dir: Path, brief: Path | None, cases: list[str], recordings_dir: Path
) -> str:
    """The session file: the cases as a work list with state. Rewritten, never appended."""
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
    lines += ["", "## Now", ""]
    pending = [c for c in cases if states[c] == "pending"]
    if pending:
        lines.append(f"Working on: `{pending[0]}`")
    else:
        lines.append("Every case has a recording.")
    lines.append(f"Updated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append("")
    return "\n".join(lines)


def write_session(
    run_dir: Path, brief: Path | None, cases: list[str], recordings_dir: Path
) -> Path:
    session = run_dir / SESSION_FILENAME
    session.write_text(render_session(run_dir, brief, cases, recordings_dir), encoding="utf-8")
    return session


# --------------------------------------------------------------------------
# entry points
# --------------------------------------------------------------------------


def tidy_one_case(
    case: str,
    run_id: str,
    runs_root: Path = DEFAULT_RUNS_ROOT,
    recordings_dir: Path = DEFAULT_RECORDINGS_DIR,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Bring one case into one run. Touches nothing else."""
    run_dir = runs_root / run_id
    if not run_dir.is_dir():
        return {"action": "no-such-run", "run_id": run_id, "case": case}

    before = classify(recordings_dir, [case])
    if dry_run:
        return {
            "action": "would-prepare",
            "dry_run": True,
            "case": case,
            "run_id": run_id,
            "would_link": before["linked"] == [case],
            "missing_py": before["missing_py"],
        }

    if case in before["linked"]:
        tidy_recordings(recordings_dir, [case])
        normalise_recordings(recordings_dir, [case])
        point_recording_at_auth(recordings_dir, case)
        linked = link_case(run_dir, recordings_dir, case)
    else:
        linked = "skipped"
    link_system_auth(runs_root, recordings_dir)
    write_session(run_dir, (find_brief(run_dir) or [None])[0], [case], recordings_dir)

    after = classify(recordings_dir, [case])
    return {
        "action": "prepared",
        "case": case,
        "run_id": run_id,
        "linked": linked,
        "missing_py": after["missing_py"],
        "ask_url_for": after["ask_url"],
        "commands": [url_request(recordings_dir, c) for c in after["ask_url"]],
    }


def prepare(
    runs_root: Path = DEFAULT_RUNS_ROOT,
    recordings_dir: Path = DEFAULT_RECORDINGS_DIR,
    run_id: str | None = None,
    cases: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Every case into one run. Link what exists; complain only about a missing .py."""
    if run_id is not None:
        run_dir = runs_root / run_id
        if not run_dir.is_dir():
            return {"action": "no-such-run", "run_id": run_id}
    else:
        run_dir = find_latest_run(runs_root)
        if run_dir is None:
            return {"action": "no-run", "root": str(runs_root)}

    brief = (find_brief(run_dir) or [None])[0]

    declared = read_cases(run_dir)
    if declared is not None:
        names = declared          # the human's list wins, and is never a reason to stop
    elif cases is not None:
        names = cases
    else:
        names = discover_cases(recordings_dir)
        if names and not dry_run:
            write_cases(run_dir, names)

    before = classify(recordings_dir, names)

    if not dry_run:
        tidy_recordings(recordings_dir, before["linked"])
        normalise_recordings(recordings_dir, before["linked"])
        for case in before["linked"]:
            point_recording_at_auth(recordings_dir, case)
        link_cases(run_dir, recordings_dir, before["linked"])
        link_system_auth(runs_root, recordings_dir)
        write_session(run_dir, brief, names, recordings_dir)

    after = classify(recordings_dir, names)
    return {
        "action": "prepared",
        "dry_run": dry_run,
        "run_id": run_dir.name,
        "brief": brief.name if brief else None,
        "linked": len(after["linked"]),           # silent — not worth case-by-case
        "missing_py": after["missing_py"],       # the only thing worth complaining about
        "ask_url_for": after["ask_url"],         # what to ask the human for next
        "commands": [url_request(recordings_dir, c) for c in after["ask_url"]],
        "session": str(run_dir / SESSION_FILENAME),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Link recordings into a run and report what needs a human.",
        epilog=(
            "tidy.py <case> <run_id>   one case into one run\n"
            "tidy.py                    every case into the latest run"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("case", nargs="?", help="case name, e.g. sales-invoice")
    parser.add_argument("run_id", nargs="?", help="target run id, e.g. 001")
    parser.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT))
    parser.add_argument(
        "--recordings", dest="recordings_dir", default=str(DEFAULT_RECORDINGS_DIR)
    )
    parser.add_argument("--run-id", dest="run_id_opt")
    parser.add_argument("--cases", help="comma-separated names, overrides discovery")
    parser.add_argument("--dry-run", action="store_true")
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
        names = [n.strip() for n in args.cases.split(",") if n.strip()] if args.cases else None
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