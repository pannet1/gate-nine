"""Run and brief discovery for the main loop.

Covers the head of the loop described in index.html §4:

1. find the latest run_id — the highest-numbered folder under the root
2. discover the .md brief inside it (name free, only the extension counts)

It stops there and reports. Deciding which documents to test, and writing
test.html, belongs to the AI reading the brief — this module does not write
anything and does not interpret prose.
"""

from pathlib import Path
from typing import Any

PLAN_FILENAME = "test.html"
BRIEF_SUFFIX = ".md"


def find_latest_run(root: Path) -> Path | None:
    """Return the highest-numbered run folder under root, or None."""
    if not root.is_dir():
        return None
    runs = [entry for entry in root.iterdir() if entry.is_dir() and entry.name.isdigit()]
    if not runs:
        return None
    return max(runs, key=lambda run: int(run.name))


def find_brief(run_dir: Path) -> list[Path]:
    """Return every .md file in the run folder, sorted by name.

    The brief may carry any name, so only the extension is matched. More than
    one is ambiguous; the caller decides how to react.
    """
    return sorted(
        entry for entry in run_dir.iterdir()
        if entry.is_file() and entry.name.lower().endswith(BRIEF_SUFFIX)
    )


def list_case_folders(run_dir: Path) -> list[Path]:
    """Return the case folders present in the run, sorted by name.

    This is a report of what is on disk, not a selection of what to test.
    """
    return sorted(entry for entry in run_dir.iterdir() if entry.is_dir())


def discover(root: Path) -> dict[str, Any]:
    """Report what the loop would find under root. Writes nothing."""
    run_dir = find_latest_run(root)
    if run_dir is None:
        return {"action": "no-run", "root": str(root)}

    briefs = find_brief(run_dir)
    result: dict[str, Any] = {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "plan_present": (run_dir / PLAN_FILENAME).exists(),
        "case_folders": [folder.name for folder in list_case_folders(run_dir)],
    }
    if not briefs:
        result["action"] = "no-brief"
        return result

    result["action"] = "brief-found"
    result["brief"] = briefs[0].name
    result["ambiguous"] = len(briefs) > 1
    return result


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Find the latest run and the brief inside it.")
    parser.add_argument("root", nargs="?", default="test-cases", help="runs root (default: test-cases)")
    args = parser.parse_args()
    print(json.dumps(discover(Path(args.root)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
