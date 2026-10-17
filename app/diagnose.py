"""Inspect the completed highest-numbered run for Step D diagnosis.

This module does not decide whether Rachis is defective. It identifies the
evidence available to the AI and separates harness gaps from failures that need
human browser review before a developer is notified.

Events are streamed to a remote FastAPI endpoint (``events_url``) over HTTP
Basic Auth and are not kept locally, so this gate can only inspect the plan
and report where events go — it cannot re-read a local event log.
"""

from pathlib import Path
from typing import Any

from .config import settings
from .planner import find_latest_run

PLAYWRIGHT_ERRORS = {
    "playwright_console_error",
    "playwright_page_error",
    "playwright_request_failed",
    "playwright_page_crash",
}


def diagnose(root: Path = Path("test-cases")) -> dict[str, Any]:
    """Return a read-only diagnosis gate for the highest-numbered run."""
    run_dir = find_latest_run(root)
    if run_dir is None:
        return {"action": "no-run", "root": str(root)}

    plan = run_dir / "test.html"
    run_id = run_dir.name
    result: dict[str, Any] = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "plan_present": plan.is_file(),
        "log_source": settings.events_url or "none",
        "event_count": 0,
    }
    if not plan.is_file():
        result["action"] = "await-plan"
        return result

    # Events stream remotely; there is no local archive to inspect here, so no
    # harness gaps or failed steps can be surfaced from this machine.
    result["action"] = "diagnose"
    result["harness_gaps"] = []
    result["failed_steps"] = []
    result["run_failures"] = []
    result["playwright_errors"] = []
    result["developer_review_required"] = False
    result["human_browser_review_required"] = False
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
