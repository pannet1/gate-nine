"""Inspect the completed highest-numbered run for Step D diagnosis.

This module does not decide whether Rachis is defective. It identifies the
evidence available to the AI and separates harness gaps from failures that need
human browser review before a developer is notified.
"""

import json
from pathlib import Path
from typing import Any

from .events import read_events
from .planner import find_latest_run


def diagnose(root: Path = Path("test-cases")) -> dict[str, Any]:
    """Return a read-only diagnosis gate for the highest-numbered run."""
    run_dir = find_latest_run(root)
    if run_dir is None:
        return {"action": "no-run", "root": str(root)}

    plan = run_dir / "test.html"
    log = run_dir / "events.jsonl"
    result: dict[str, Any] = {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "plan_present": plan.is_file(),
        "log_present": log.is_file(),
    }
    if not plan.is_file():
        result["action"] = "await-plan"
        return result
    if not log.is_file():
        result["action"] = "await-log"
        return result

    events = read_events(log)
    result["action"] = "diagnose"
    result["event_count"] = len(events)
    result["harness_gaps"] = [
        event for event in events if event.get("action") == "step_no_handler"
    ]
    result["failed_steps"] = [
        event for event in events if event.get("action") == "step_failed"
    ]
    result["run_failures"] = [
        event for event in events if event.get("action") == "run_failed"
    ]
    result["developer_review_required"] = bool(result["failed_steps"] or result["run_failures"])
    result["human_browser_review_required"] = bool(
        result["harness_gaps"] or result["failed_steps"] or result["run_failures"]
    )
    result["product_bug_status"] = "undetermined"
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Inspect the completed highest-numbered run.")
    parser.add_argument("root", nargs="?", default="test-cases")
    args = parser.parse_args()
    print(json.dumps(diagnose(Path(args.root)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
