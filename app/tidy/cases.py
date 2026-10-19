"""The case list: what exists, and what the human declared.

Nothing here interprets prose. Cases come from `cases.yml` when the human has
written one, otherwise from what is on disk.
"""

from pathlib import Path

import yaml

RECORDING_SUFFIX = ".py"
CASES_FILENAME = "cases.yml"

_HEADER = (
    "# Cases interpreted from the brief.\n"
    "# Correct this freely — the run reads this file in preference to\n"
    "# anything inferred, and never overwrites it.\n"
)


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
    path.write_text(
        _HEADER + yaml.safe_dump({"cases": list(cases)}, sort_keys=False, allow_unicode=True),
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
        e.stem
        for e in recordings_dir.iterdir()
        if e.is_file() and e.suffix == RECORDING_SUFFIX
    }
    return sorted(names)


def has_recording(recordings_dir: Path, case: str) -> bool:
    """Whether a case has a recording, loose or already in its folder.

    Any .py in the case folder counts, even a drifted filename — that is a
    recording awaiting a rename, not a missing one.
    """
    case_dir = recordings_dir / case
    if (recordings_dir / f"{case}{RECORDING_SUFFIX}").exists():
        return True
    return case_dir.is_dir() and any(
        e.suffix == RECORDING_SUFFIX for e in case_dir.iterdir() if e.is_file()
    )


def has_url(recordings_dir: Path, case: str) -> bool:
    return (recordings_dir / case / "url.txt").is_file()


def classify(recordings_dir: Path, cases: list[str]) -> dict[str, list[str]]:
    """Split the cases three ways. This is the whole rule.

    - a case that has a recording -> linked, silently
    - a case without one           -> the only thing worth complaining about
    - a linked case with no url.txt -> what to ask the human for next
    """
    linked: list[str] = []
    missing_py: list[str] = []
    ask_url: list[str] = []
    for case in cases:
        if has_recording(recordings_dir, case):
            linked.append(case)
            if not has_url(recordings_dir, case):
                ask_url.append(case)
        else:
            missing_py.append(case)
    return {"linked": linked, "missing_py": missing_py, "ask_url": ask_url}