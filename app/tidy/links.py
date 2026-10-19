"""Symlinks. Nothing here ever replaces a link with a copy, or touches a real
directory that is standing where a link belongs.
"""

import os
from pathlib import Path

# test-cases/<run>/<case> -> ../../recordings/<case>
CASE_TARGET = Path("..") / ".." / "recordings"
# test-cases/auth.json -> ../recordings/auth.json
AUTH_TARGET = Path("..") / "recordings" / "auth.json"


def _same_link(link: Path, target: Path) -> bool:
    return Path(os.path.normpath(os.readlink(link))) == Path(os.path.normpath(target))


def link_case(run_dir: Path, case: str) -> str:
    """Point test-cases/<run>/<case> at recordings/<case>.

    Returns created, already-linked, repaired, or skipped when a real file or
    directory is in the way.
    """
    link = run_dir / case
    target = CASE_TARGET / case

    if link.is_symlink():
        if _same_link(link, target):
            return "already-linked"
        link.unlink()
        link.symlink_to(target, target_is_directory=True)
        return "repaired"
    if link.exists():
        return "skipped"
    link.symlink_to(target, target_is_directory=True)
    return "created"


def link_cases(run_dir: Path, cases: list[str]) -> dict[str, str]:
    return {case: link_case(run_dir, case) for case in cases}


def link_system_auth(runs_root: Path, recordings_dir: Path) -> str:
    """Ensure test-cases/auth.json points at the one real file in recordings/.

    Neither file nor link is ever committed — the gitignore pattern for
    auth.json covers both, so no dangling link enters the repo.
    """
    link = runs_root / "auth.json"
    if link.is_symlink():
        if _same_link(link, AUTH_TARGET):
            return "already-linked"
        link.unlink()
    elif link.exists():
        return "skipped"
    if not (recordings_dir / "auth.json").exists():
        return "no-auth-file"
    link.symlink_to(AUTH_TARGET)
    return "created"