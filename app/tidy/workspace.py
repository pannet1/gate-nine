"""The interface a main loop consumes.

    ws = Workspace()                        # defaults to test-cases/ and recordings/
    report = ws.sync_case("sales-invoice", "001")
    report = ws.sync_run("002")

`sync_case` and `sync_run` are idempotent and return a plain dict, so a loop can
branch on it without importing anything else. Both take a `Workspace` rather
than loose paths, so a caller never has to know the layout.
"""

from pathlib import Path
from typing import Any

from ..planner import find_brief, find_latest_run
from .cases import (
    classify,
    discover_cases,
    read_cases,
    write_cases,
)
from .files import append_screenshot_and_slow_mo, normalise_recordings, point_recording_at_auth, tidy_recordings
from .links import link_cases, link_system_auth
from .session import SESSION_FILENAME, write_session

DEFAULT_RUNS_ROOT = Path("test-cases")
DEFAULT_RECORDINGS_DIR = Path("recordings")


def url_request(recordings_dir: Path, case: str) -> str:
    """The line to hand over when a case needs its URL."""
    return f"echo '<url>' > {recordings_dir}/{case}/url.txt"


class Workspace:
    """The recordings area and the runs it feeds."""

    def __init__(
        self,
        runs_root: Path | str = DEFAULT_RUNS_ROOT,
        recordings_dir: Path | str = DEFAULT_RECORDINGS_DIR,
    ) -> None:
        self.runs_root = Path(runs_root)
        self.recordings_dir = Path(recordings_dir)

    # -- introspection ----------------------------------------------------

    def latest_run(self) -> Path | None:
        return find_latest_run(self.runs_root)

    def cases_for(self, run_id: str | None = None, *, dry_run: bool = False) -> list[str]:
        """The cases a run covers: cases.yml if the human wrote one, else disk."""
        run_dir = self.runs_root / run_id if run_id else self.latest_run()
        if run_dir is None or not run_dir.is_dir():
            return []
        declared = read_cases(run_dir)
        if declared is not None:
            return declared
        return discover_cases(self.recordings_dir)

    def classify(self, cases: list[str]) -> dict[str, list[str]]:
        """linkable / missing a .py / missing a url.txt, for any case list."""
        return classify(self.recordings_dir, cases)

    # -- the work ----------------------------------------------------------

    def _prepare_files(self, cases: list[str]) -> None:
        """Move, rename, point at auth, and make recordings watchable."""
        tidy_recordings(self.recordings_dir, cases)
        normalise_recordings(self.recordings_dir, cases)
        for case in cases:
            point_recording_at_auth(self.recordings_dir, case)
            append_screenshot_and_slow_mo(self.recordings_dir, case)

    def sync_case(self, case: str, run_id: str | None = None, *, dry_run: bool = False) -> dict[str, Any]:
        """Bring one case into one run. Touches nothing else."""
        run_dir = self.runs_root / run_id if run_id else self.latest_run()
        if run_dir is None:
            return {"action": "no-run", "root": str(self.runs_root)}
        if not run_dir.is_dir():
            return {"action": "no-such-run", "run_id": run_id, "case": case}

        before = classify(self.recordings_dir, [case])
        if dry_run:
            return {
                "action": "would-prepare",
                "dry_run": True,
                "case": case,
                "run_id": run_dir.name,
                "would_link": before["linked"] == [case],
                "missing_py": before["missing_py"],
            }

        if case in before["linked"]:
            self._prepare_files([case])
            linked = link_cases(run_dir, [case])[case]
        else:
            linked = "skipped"
        link_system_auth(self.runs_root, self.recordings_dir)
        write_session(run_dir, self._brief(run_dir), [case], self.recordings_dir)

        after = classify(self.recordings_dir, [case])
        return {
            "action": "prepared",
            "case": case,
            "run_id": run_dir.name,
            "linked": linked,
            "missing_py": after["missing_py"],
            "ask_url_for": after["ask_url"],
            "commands": [url_request(self.recordings_dir, c) for c in after["ask_url"]],
        }

    def sync_run(self, run_id: str | None = None, *, cases: list[str] | None = None,
                 dry_run: bool = False) -> dict[str, Any]:
        """Bring every case into one run. Link what exists; report what does not."""
        if run_id:
            run_dir = self.runs_root / run_id
        else:
            run_dir = self.latest_run()
        if run_dir is None:
            return {"action": "no-run", "root": str(self.runs_root)}
        if not run_dir.is_dir():
            return {"action": "no-such-run", "run_id": run_id}

        brief = self._brief(run_dir)
        if read_cases(run_dir) is not None:
            names = read_cases(run_dir)          # the human's list wins, never a stop
        elif cases is not None:
            names = cases
        else:
            names = discover_cases(self.recordings_dir)
            if names and not dry_run:
                write_cases(run_dir, names)

        before = classify(self.recordings_dir, names)
        if not dry_run:
            self._prepare_files(before["linked"])
            link_cases(run_dir, before["linked"])
            link_system_auth(self.runs_root, self.recordings_dir)
            write_session(run_dir, brief, names, self.recordings_dir)

        after = classify(self.recordings_dir, names)
        return {
            "action": "prepared",
            "dry_run": dry_run,
            "run_id": run_dir.name,
            "brief": brief.name if brief else None,
            "linked": len(after["linked"]),      # silent — not worth case by case
            "missing_py": after["missing_py"],   # the only thing worth complaining about
            "ask_url_for": after["ask_url"],     # what to ask the human for next
            "commands": [url_request(self.recordings_dir, c) for c in after["ask_url"]],
            "session": str(run_dir / SESSION_FILENAME),
        }

    @staticmethod
    def _brief(run_dir: Path) -> Path | None:
        briefs = find_brief(run_dir)
        return briefs[0] if briefs else None