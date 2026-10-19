"""Fixing up the files a human left — moving, renaming, pointing at auth.

Every function here is idempotent and refuses to overwrite anything it did not
create. They never delete a recording.
"""

import re
from pathlib import Path

from .cases import RECORDING_SUFFIX

# Where the one system-wide auth.json lives, relative to a case folder.
AUTH_RELATIVE = "../auth.json"

_STORAGE_STATE = r"""(storage_state=)(["'])[^"']*(["'])"""


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
            names = ", ".join(c.name for c in candidates)
            fixed.append(f"{case_dir.name} (ambiguous: {names})")
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
    if not re.search(_STORAGE_STATE, source):
        return "nothing-to-rewrite"
    updated = re.sub(_STORAGE_STATE, rf"\g<1>\g<2>{AUTH_RELATIVE}\g<3>", source)
    if updated == source:
        return "nothing-to-rewrite"
    recording.write_text(updated, encoding="utf-8")
    return "rewritten"