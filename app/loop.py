"""Main loop — gate on the run's test.html, then open a visible browser.

Follows index.html §4: find the latest run_id, confirm test.html exists, and
only then start Chromium with a window the human can watch. When test.html is
absent the loop stops and reports — creating it belongs to the AI reading the
brief, never to this module.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from .config import settings
from .events import append_event
from .planner import discover

# The loop is deliberately visible. A human has to be able to watch fields get
# filled and stop the run when something looks wrong, so headless is not
# offered here regardless of what the setting says.
HEADLESS = False


def gate(root: Path) -> dict[str, Any]:
    """Decide what the loop should do. Writes nothing."""
    report = discover(root)

    if report.get("action") == "no-run":
        report["loop"] = "stop"
        report["reason"] = "no run_id folder found"
        return report

    if not report.get("plan_present"):
        report["loop"] = "await-plan"
        report["reason"] = "test.html absent — the AI must create it before the loop runs"
        return report

    report["loop"] = "run-browser"
    return report


async def run_visible(run_dir: Path) -> None:
    """Open the tenant in a visible window and stay open until it is closed.

    Only navigation and login filling happen here. Executing the plan's steps
    needs voucher handlers, which do not exist yet — the window is held open
    so a human can inspect the starting state.
    """
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=HEADLESS)
        page = await browser.new_page()
        await page.goto(settings.rachis_base_url, wait_until="domcontentloaded")
        append_event(
            settings.event_log_path,
            test_id=run_dir.name,
            action="open_url",
            details={"url": settings.rachis_base_url, "plan": str(run_dir / "test.html")},
        )

        if settings.rachis_username and await page.locator("input[type=email], input[name=username]").count():
            await page.locator("input[type=email], input[name=username]").first.fill(settings.rachis_username)
            append_event(settings.event_log_path, test_id=run_dir.name, action="fill_username")
        if settings.rachis_password and await page.locator("input[type=password]").count():
            await page.locator("input[type=password]").first.fill(settings.rachis_password)
            append_event(settings.event_log_path, test_id=run_dir.name, action="fill_password")

        # Hold the loop open until the window is shut by hand.
        await page.wait_for_event("close")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the loop: gate on test.html, open a visible browser.")
    parser.add_argument("root", nargs="?", default="test-cases", help="runs root (default: test-cases)")
    parser.add_argument("--check", action="store_true", help="print the gate decision without opening a browser")
    args = parser.parse_args()

    report = gate(Path(args.root))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["loop"] != "run-browser":
        return
    if args.check:
        return
    asyncio.run(run_visible(Path(report["run_dir"])))


if __name__ == "__main__":
    main()
