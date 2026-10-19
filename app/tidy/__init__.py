"""Bring recordings into a run.

The mechanical part of the loop, in code so no judgement is spent per pass.

    uv run python -m app.tidy sales-invoice 001   one case into one run
    uv run python -m app.tidy                      every case into the latest run
    uv run python -m app.tidy ... --dry-run       report without moving anything

A main loop should drive `Workspace` rather than the CLI:

    from app.tidy import Workspace
    ws = Workspace()
    report = ws.sync_run("002")
    if report["missing_py"]:
        ...   # hand over report["commands"] and stop

The rule is deliberately small:

    a case that has a recording   -> linked, silently
    a case that has none          -> the only thing worth complaining about
    a linked case with no url.txt -> what to ask the human for next

Nothing is inferred from prose. The case list is read from cases.yml when it
exists, and written from what is on disk only when it does not.
"""

from .cases import (
    CASES_FILENAME,
    classify,
    discover_cases,
    case_folders,
    has_recording,
    has_url,
    read_cases,
    write_cases,
)
from .cli import main
from .files import AUTH_RELATIVE, normalise_recordings, point_recording_at_auth, tidy_recordings
from .links import link_case, link_cases, link_system_auth
from .session import case_state, render_session, write_session
from .workspace import Workspace, url_request

__all__ = [
    "AUTH_RELATIVE",
    "CASES_FILENAME",
    "Workspace",
    "case_folders",
    "case_state",
    "classify",
    "discover_cases",
    "has_recording",
    "has_url",
    "link_case",
    "link_cases",
    "link_system_auth",
    "main",
    "normalise_recordings",
    "point_recording_at_auth",
    "read_cases",
    "render_session",
    "tidy_recordings",
    "url_request",
    "write_cases",
    "write_session",
]


def tidy_one_case(
    case: str,
    run_id: str,
    runs_root=None,
    recordings_dir=None,
    dry_run: bool = False,
) -> dict:
    """Backwards-compatible shim. Prefer ``Workspace.sync_case``."""
    from pathlib import Path

    from .workspace import DEFAULT_RECORDINGS_DIR, DEFAULT_RUNS_ROOT

    ws = Workspace(
        runs_root=Path(runs_root) if runs_root else DEFAULT_RUNS_ROOT,
        recordings_dir=Path(recordings_dir) if recordings_dir else DEFAULT_RECORDINGS_DIR,
    )
    return ws.sync_case(case, run_id, dry_run=dry_run)


def prepare(
    runs_root=None,
    recordings_dir=None,
    run_id: str | None = None,
    cases: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Backwards-compatible shim. Prefer ``Workspace.sync_run``."""
    from pathlib import Path

    from .workspace import DEFAULT_RECORDINGS_DIR, DEFAULT_RUNS_ROOT

    ws = Workspace(
        runs_root=Path(runs_root) if runs_root else DEFAULT_RUNS_ROOT,
        recordings_dir=Path(recordings_dir) if recordings_dir else DEFAULT_RECORDINGS_DIR,
    )
    return ws.sync_run(run_id=run_id, cases=cases, dry_run=dry_run)