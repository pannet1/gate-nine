"""Drive a run's test.html in a visible browser, unattended.

Playwright executes the plan start to finish. Nothing waits for input: each
step runs, the window holds for a fixed pause so human eyes can follow what was
entered, and the next step fires. The browser is never headless — seeing fields
get entered is the point of the project (index.html §1).

Each step's outcome is appended to the JSONL event log, so a run leaves a
machine-readable record of what it did and where it stopped.

How a step is classified:
    ok          the action ran.
    no-handler  this harness has no driver for the action yet — a gap in the
                tool, not a failure of the product. Recorded, then the run
                continues past it.
    failed      the action was attempted and did not succeed. The run stops
                here: continuing from a broken state only produces noise.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, NamedTuple

from .config import settings
from .events import append_event

HEADLESS = False
PLAN_MARKER = 'id="plan"'

# The marketing homepage is served at the base URL, so signing in has to reach
# this route explicitly rather than assuming the landing page is the app.
LOGIN_ROUTE = "/login/"

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

# Actions the harness actually completes. Everything else opens a voucher at
# most, which is not the action asked for and must not be reported as done —
# opening a form is not printing it, and it is not posting a correction.
ROUTED_ACTIONS = {"open-new"}


class Outcome(NamedTuple):
    """What became of one step."""

    status: str  # "ok" | "no-handler" | "failed"
    detail: str = ""


def _normalise(case: str) -> str:
    """Fold a case folder name down to its route lookup key.

    Folders are hyphenated slugs — sales-invoice, goods-receipt — and routes
    are keyed on spaced names, so hyphens and runs of space fold together.
    """
    return re.sub(r"[\s-]+", " ", case).strip().lower()


def route_for(case: str) -> str | None:
    """The new-voucher route for a case folder, or None if it has none."""
    return VOUCHER_ROUTES.get(_normalise(case))


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
    """Name the step and point at its case folder — never restate the method.

    How to test lives in app/vouchers/<case>/test-case.html and nowhere else.
    The plan carries the order; the case carries the steps.
    """
    case = step.get("case", "")
    print(f"\n[{index}/{total}] step {step['id']} · {step.get('action', '')} · {case}/")
    print(f"    method:  app/vouchers/{case}/test-case.html")


async def drive(run_dir: Path) -> dict[str, Any]:
    """Run the whole plan in a visible browser, unattended."""
    from playwright.async_api import async_playwright

    plan = parse_plan(plan_path(run_dir))
    steps: list[dict[str, Any]] = plan.get("steps", [])
    run_id = plan.get("run_id", run_dir.name)
    summary: dict[str, Any] = {
        "run_id": run_id,
        "total": len(steps),
        "counts": {"ok": 0, "no-handler": 0, "failed": 0},
        "failed": None,
    }

    if not steps:
        summary["failed"] = {"step": None, "detail": "empty-plan"}
        return summary

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=HEADLESS)
        page = await browser.new_page()
        # No bootstrap sign-in here. The plan's sign-in step owns it, so a run
        # logs one POST rather than one here and another at step 0.

        for index, step in enumerate(steps):
            announce(step, index + 1, len(steps))
            outcome = await _perform(page, run_id, step)
            summary["counts"][outcome.status] += 1
            print(f"    → {outcome.status}" + (f" — {outcome.detail}" if outcome.detail else ""))
            _log(
                run_id,
                f"step_{outcome.status.replace('-', '_')}",
                {"id": step["id"], "action": step.get("action"), "detail": outcome.detail},
            )
            if outcome.status == "ok":
                pass
            elif outcome.status == "no-handler":
                # A gap in the harness, not a failure of the product. Keep going
                # so one unwritten action does not hide the rest of the run.
                pass
            else:
                summary["failed"] = {"step": step["id"], "detail": outcome.detail}
                break

            # Hold on the result so a human watching the window can see what was
            # entered before the next action moves on.
            if index + 1 < len(steps):
                await asyncio.sleep(settings.step_delay)

        await browser.close()

    _log(run_id, "run_result", summary["counts"])
    counts = summary["counts"]
    print(
        f"  {counts['ok']} ok · {counts['no-handler']} no handler · {counts['failed']} failed"
        + (f" — stopped at step {summary['failed']['step']}" if summary["failed"] else "")
    )
    return summary


async def _sign_in(page: Any, run_id: str) -> Outcome:
    """Sign in from .env, or report why the window is past the login.

    The tenant's login form is POST-based with fields `email` and `password`;
    nothing here is submitted anywhere else.

    The base URL is the marketing site, not the app, so landing on it is not
    evidence of being signed in — the login route has to be reached first.
    """
    if "login" not in page.url:
        await page.goto(
            settings.rachis_base_url.rstrip("/") + LOGIN_ROUTE, wait_until="domcontentloaded"
        )
        # Already inside and bounced onward? Then there is nothing to fill.
        if "login" not in page.url:
            _log(run_id, "sign_in_ok", {"url": page.url, "already": True})
            return Outcome("ok")

    email = page.locator("input[type=email]")
    password = page.locator("input[type=password]")
    try:
        # Wait rather than sample: the form may still be rendering after goto,
        # and a snapshot here reads a missing form as a login failure.
        await email.first.wait_for(state="visible", timeout=15000)
        await password.first.wait_for(state="visible", timeout=15000)
    except Exception:  # noqa: BLE001 - the form genuinely did not arrive
        return Outcome("failed", f"no login form at {page.url}")

    if not settings.rachis_username or not settings.rachis_password:
        return Outcome("failed", "no credentials in .env")

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
    try:
        await page.wait_for_url(lambda url: "login" not in url, timeout=15000)
    except Exception:  # noqa: BLE001 - still on the form means it was refused
        return Outcome("failed", "still on the login form after submitting")
    _log(run_id, "sign_in_ok", {"url": page.url})
    return Outcome("ok")


async def _perform(page: Any, run_id: str, step: dict[str, Any]) -> Outcome:
    """Attempt a step's action and say how it went."""
    action = step.get("action", "")
    case = step.get("case", "")
    try:
        if action == "sign-in":
            return await _sign_in(page, run_id)
        if action in ROUTED_ACTIONS:
            return await _open_voucher(page, run_id, case)
        # No driver written for this action yet. Opening the voucher would not
        # be the action asked for, so it is recorded as a gap, never as a pass.
        return Outcome("no-handler", f"no handler for action '{action}'")
    except Exception as exc:  # noqa: BLE001 - a crash is a failure, not a traceback
        return Outcome("failed", f"{type(exc).__name__}: {exc}")


async def _open_voucher(page: Any, run_id: str, case: str) -> Outcome:
    """Open a blank voucher by navigating to its case folder's route.

    Route-first rather than control-first: a new-voucher button is not present
    on every page, so label-hunting only worked when one happened to be on
    screen. Navigation works from anywhere. A case with no known route falls
    through to label-hunting; failing that it is reported as a gap in the
    harness rather than a wrong click.

    Routes confirmed against the live tenant on 2026-10-17.
    """
    route = route_for(case)
    if route:
        await page.goto(settings.rachis_base_url.rstrip("/") + route, wait_until="domcontentloaded")
        # The tenant is client-rendered, so domcontentloaded lands before the
        # heading exists. Wait for it rather than sampling once — count() here
        # was a snapshot, which made every voucher look like it failed to open.
        heading = page.get_by_role("heading", level=1).first
        try:
            await heading.wait_for(state="visible", timeout=15000)
        except Exception:  # noqa: BLE001 - the product did not render the voucher
            return Outcome("failed", f"route {route} never showed a heading")
        name = (await heading.inner_text()).strip()
        _log(run_id, "open_voucher", {"case": case, "route": route, "heading": name})
        return Outcome("ok")

    label = _normalise(case)
    candidates = [
        page.get_by_role("link", name=re.compile(label, re.I)),
        page.get_by_role("button", name=re.compile(label, re.I)),
        page.get_by_text(re.compile(rf"^\s*new\s+{re.escape(label)}\b", re.I)),
    ]
    for locator in candidates:
        if await locator.count():
            await locator.first.click(timeout=4000)
            _log(run_id, "open_voucher", {"case": case, "via": "label"})
            return Outcome("ok")
    return Outcome("no-handler", f"no route for '{case}/' and no control on this page")


def _log(run_id: str, action: str, details: dict[str, Any]) -> None:
    append_event(settings.event_log_path, test_id=run_id, action=action, details=details)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Drive a run's test.html in a visible browser.")
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
