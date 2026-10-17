"""Drive a run's test.html in a visible browser, with a human able to take over.

Playwright executes the plan; the human watches and intervenes where needed.
The browser is never headless — seeing fields get entered is the point of the
project (index.html §1).

Commands between steps:
    Enter   continue to the next step
    p       pause — stop driving, leave the browser open for manual work
    r       restart the flow from step 1
    q       quit

An action with no handler is not a failure: it is an intervention point. The
driver stops, says what it could not do, and hands the window to the human.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from .config import settings
from .events import append_event

HEADLESS = False
PLAN_MARKER = 'id="plan"'

# New-voucher routes, read off the live tenant 2026-10-17. The plan's voucher
# names are normalised before lookup, so "GRN" reaches the route whose own
# heading reads "Goods Receipt".
VOUCHER_ROUTES = {
    "sales invoice": "/accounting/sales-invoices/new/",
    "purchase bill": "/accounting/bills/new/",
    "grn": "/accounting/grns/new/",
    "goods receipt": "/accounting/grns/new/",
    "credit note": "/accounting/credit-notes/new/",
    "debit note": "/accounting/debit-notes/new/",
}


def _normalise(voucher: str) -> str:
    """Fold a plan's voucher name down to its lookup key."""
    return re.sub(r"\s+", " ", voucher).strip().lower()


def route_for(voucher: str) -> str | None:
    """The new-voucher route for a plan's voucher name, or None if unknown."""
    return VOUCHER_ROUTES.get(_normalise(voucher))


def parse_plan(test_html: Path) -> dict[str, Any]:
    """Read the JSON plan block out of a generated test.html.

    The prose tables in that file are for humans; only this block drives code.
    """
    if not test_html.is_file():
        raise FileNotFoundError(f"no plan at {test_html}")
    text = test_html.read_text(encoding="utf-8")
    start = text.find("<script", text.find(PLAN_MARKER) - 60 if PLAN_MARKER in text else 0)
    if PLAN_MARKER not in text:
        raise ValueError(f"{test_html} has no plan block")
    start = text.index(">", text.index("<script", start)) + 1
    end = text.index("</script>", start)
    return json.loads(text[start:end])


def plan_path(run_dir: Path) -> Path:
    return run_dir / "test.html"


def announce(step: dict[str, Any], index: int, total: int) -> None:
    print(f"\n[{index}/{total}] step {step['id']} · {step.get('test', '')} · {step.get('action', '')}")
    print(f"    voucher: {step.get('voucher', '?')}")
    print(f"    check:   {step.get('check', '')}")


async def prompt() -> str:
    """Ask the human what to do next, without blocking the event loop."""
    line = await asyncio.to_thread(input, "\n  [Enter]=next  p=pause  r=restart  q=quit > ")
    return line.strip().lower()


async def drive(run_dir: Path) -> dict[str, Any]:
    """Run the plan in a visible browser until finished, paused, or quit."""
    plan = parse_plan(plan_path(run_dir))
    steps: list[dict[str, Any]] = plan.get("steps", [])
    run_id = plan.get("run_id", run_dir.name)
    summary: dict[str, Any] = {"run_id": run_id, "total": len(steps), "completed": [], "stopped": None}

    if not steps:
        summary["stopped"] = "empty-plan"
        return summary

    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=HEADLESS)
        page = await browser.new_page()
        await page.goto(settings.rachis_base_url, wait_until="domcontentloaded")
        _log(run_id, "open_url", {"url": settings.rachis_base_url})
        signed_in = await _sign_in(page, run_id)
        if signed_in != "ok":
            print(f"    ! {signed_in}")

        index = 0
        while index < len(steps):
            step = steps[index]
            announce(step, index + 1, len(steps))

            outcome = await _perform(page, run_id, step)
            if outcome != "ok":
                print(f"    ! {outcome} — the window is yours. Fix it, then choose below.")

            command = await prompt()
            if command == "q":
                summary["stopped"] = "quit"
                summary["at"] = step["id"]
                break
            if command == "r":
                print("    restarting from step 1")
                _log(run_id, "restart", {"at": step["id"]})
                await page.goto(settings.rachis_base_url, wait_until="domcontentloaded")
                if await _sign_in(page, run_id) != "ok":
                    print("    ! still not signed in after restart — the window is yours")
                index = 0
                summary["completed"].clear()
                continue
            if command == "p":
                print("    paused — drive the browser by hand. Re-run to resume.")
                _log(run_id, "pause", {"at": step["id"]})
                summary["stopped"] = "paused"
                summary["at"] = step["id"]
                break

            if outcome == "ok":
                summary["completed"].append(step["id"])
                _log(run_id, "step_ok", {"id": step["id"], "action": step.get("action")})
            index += 1

        # The window closes itself, unless the human asked to take it over.
        if summary["stopped"] == "paused":
            print("\n  browser is yours — close the window when you are done.")
            await page.wait_for_event("close")
        else:
            await browser.close()
            print(f"\n  done at {len(summary['completed'])}/{len(steps)} steps — browser closed.")

    return summary


async def _sign_in(page: Any, run_id: str) -> str:
    """Sign in from .env, or report that the window is already past the login.

    Returns 'ok' when signed in or already inside, and a reason to hand over
    when it cannot tell. The tenant's login form is POST-based with fields
    `email` and `password`; nothing here is submitted anywhere else.
    """
    if "login" not in page.url:
        return "ok"  # already inside — no form to fill

    email = page.locator("input[type=email]")
    password = page.locator("input[type=password]")
    try:
        # Wait rather than sample: the form may still be rendering after goto,
        # and a snapshot here reads a missing form as a login failure.
        await email.first.wait_for(state="visible", timeout=15000)
        await password.first.wait_for(state="visible", timeout=15000)
    except Exception:  # noqa: BLE001 - no form is a handover, not a crash
        return f"no login form at {page.url} — sign in yourself"

    if not settings.rachis_username or not settings.rachis_password:
        return "no credentials in .env — sign in yourself"

    await email.first.fill(settings.rachis_username)
    await password.first.fill(settings.rachis_password)
    _log(run_id, "sign_in", {"user": settings.rachis_username})

    submit = page.get_by_role("button", name=re.compile(r"^\s*sign in", re.I))
    try:
        await submit.first.wait_for(state="visible", timeout=5000)
        await submit.first.click()
    except Exception:  # noqa: BLE001 - no button is fine, Enter submits the form
        await password.first.press("Enter")

    # Wait for the POST to settle rather than sleeping on a guess.
    await page.wait_for_url(lambda url: "login" not in url, timeout=15000)
    _log(run_id, "sign_in_ok", {"url": page.url})
    return "ok"


async def _perform(page: Any, run_id: str, step: dict[str, Any]) -> str:
    """Attempt a step's action. Returns 'ok' or a human-readable reason it needs a human."""
    action = step.get("action", "")
    voucher = step.get("voucher", "")
    try:
        if action in {"open-new", "print", "draft-post-correct"}:
            return await _open_voucher(page, run_id, voucher)
        return (
            f"no handler for action '{action}' on {voucher} — the voucher handlers are not "
            "written yet, so this step is yours"
        )
    except Exception as exc:  # noqa: BLE001 - a failed action must hand over, not crash
        return f"step failed: {type(exc).__name__}: {exc}"


async def _open_voucher(page: Any, run_id: str, voucher: str) -> str:
    """Open a blank voucher by navigating to its route.

    Route-first rather than control-first: a new-voucher button is not present
    on every page, so label-hunting only worked when one happened to be on
    screen. Navigation works from anywhere. A voucher with no known route still
    falls through to label-hunting, and failing that becomes an intervention
    point rather than a wrong click.

    Routes confirmed against the live tenant on 2026-10-17.
    """
    route = VOUCHER_ROUTES.get(_normalise(voucher))
    if route:
        await page.goto(settings.rachis_base_url.rstrip("/") + route, wait_until="domcontentloaded")
        # The tenant is client-rendered, so domcontentloaded lands before the
        # heading exists. Wait for it rather than sampling once — count() here
        # was a snapshot, which made every voucher look like it failed to open.
        heading = page.get_by_role("heading", level=1).first
        try:
            await heading.wait_for(state="visible", timeout=15000)
        except Exception:  # noqa: BLE001 - a voucher that never renders hands over
            return f"route {route} never showed a heading — check the window"
        name = (await heading.inner_text()).strip()
        _log(run_id, "open_voucher", {"voucher": voucher, "route": route, "heading": name})
        return "ok"

    label = _normalise(voucher)
    candidates = [
        page.get_by_role("link", name=re.compile(label, re.I)),
        page.get_by_role("button", name=re.compile(label, re.I)),
        page.get_by_text(re.compile(rf"^\s*new\s+{re.escape(label)}\b", re.I)),
    ]
    for locator in candidates:
        if await locator.count():
            await locator.first.click(timeout=4000)
            _log(run_id, "open_voucher", {"voucher": voucher, "via": "label"})
            return "ok"
    return f"no route for '{label}' and no control on this page — open it yourself"


def _log(run_id: str, action: str, details: dict[str, Any]) -> None:
    append_event(settings.event_log_path, test_id=run_id, action=action, details=details)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Drive a run's test.html with a human in the loop.")
    parser.add_argument("root", nargs="?", default="test-cases", help="runs root (default: test-cases)")
    parser.add_argument("--plan", help="explicit path to a test.html, bypassing run discovery")
    args = parser.parse_args()

    from .planner import find_latest_run

    if args.plan:
        run_dir = Path(args.plan).parent
    else:
        run_dir = find_latest_run(Path(args.root))
        if run_dir is None:
            raise SystemExit("no run_id folder found")

    print(json.dumps(asyncio.run(drive(run_dir)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
