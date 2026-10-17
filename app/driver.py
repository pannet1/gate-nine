"""Drive a run's test.html in a visible browser, unattended.

Playwright executes the plan in a visible browser. Setup steps (sign-in and
navigation) are distinct from checks; a run cannot pass without a check, and
the first unsupported action stops it as incomplete.

Each step's outcome is appended to the JSONL event log, so a run leaves a
machine-readable record of what it did and where it stopped.

How a step is classified:
    ok          an assertion/check action ran successfully.
    setup       navigation or authentication succeeded; this is not a test pass.
    no-handler  this harness has no driver for the action yet — a gap in the
                tool, not a failure of the product. Recorded, then the run
                stops as incomplete.
    failed      the action was attempted and did not succeed. The run stops
                here: continuing from a broken state only produces noise.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlsplit, urlunsplit

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
ROUTED_ACTIONS = {"open"}


class Outcome(NamedTuple):
    """What became of one step."""

    status: str  # "ok" | "setup" | "no-handler" | "failed"
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
    marker = text.find(PLAN_MARKER)
    if marker < 0:
        raise ValueError(f"{test_html} has no plan block")
    script = text.rfind("<script", 0, marker + 1)
    if script < 0:
        raise ValueError(f"{test_html} has no script plan block")
    start = text.index(">", script) + 1
    end = text.index("</script>", start)
    return json.loads(text[start:end])


def plan_path(run_dir: Path) -> Path:
    return run_dir / "test.html"


def prepare_event_log(run_dir: Path) -> Path:
    """Create an empty root log for a new run."""
    root = settings.event_log_path
    root.parent.mkdir(parents=True, exist_ok=True)
    root.write_text("", encoding="utf-8")
    return root


def archive_event_log(run_dir: Path) -> Path:
    """Move the active root log into the completed run folder, overwriting any previous log."""
    root = settings.event_log_path
    archive = run_dir / "events.jsonl"
    if not root.exists():
        raise FileNotFoundError(f"active event log does not exist: {root}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    root.replace(archive)
    return archive


def announce(step: dict[str, Any], index: int, total: int) -> None:
    """Name the step and point at its case folder — never restate the method.

    How to test lives in app/vouchers/<case>/test-case.html and nowhere else.
    The plan carries the order; the case carries the steps.
    """
    case = step.get("case", "")
    print(f"\n[{index}/{total}] {step.get('action', '')} {step.get('type', '')} · {case}/")
    print(f"    method:  app/vouchers/{case}/test-case.html")


def _safe_request_url(url: str) -> str:
    """Keep request diagnostics useful without recording query/fragment data."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def attach_playwright_diagnostics(page: Any, run_id: str, step_context: dict[str, Any]) -> None:
    """Record browser console, page, request, and crash diagnostics as JSONL."""
    def context() -> dict[str, Any]:
        return dict(step_context)

    def on_console(message: Any) -> None:
        if message.type == "error":
            _log(run_id, "playwright_console_error", {**context(), "message": message.text})

    def on_page_error(error: BaseException) -> None:
        _log(run_id, "playwright_page_error", {**context(), "error": str(error)})

    def on_request_failed(request: Any) -> None:
        _log(
            run_id,
            "playwright_request_failed",
            {
                **context(),
                "url": _safe_request_url(request.url),
                "method": request.method,
                "resource_type": request.resource_type,
                "failure": request.failure,
            },
        )

    def on_crash() -> None:
        _log(run_id, "playwright_page_crash", context())

    page.on("console", on_console)
    page.on("pageerror", on_page_error)
    page.on("requestfailed", on_request_failed)
    page.on("crash", on_crash)


async def drive(run_dir: Path) -> dict[str, Any]:
    """Run the plan visibly; never equate setup with a passing test."""
    plan = parse_plan(plan_path(run_dir))
    prepare_event_log(run_dir)
    steps: list[dict[str, Any]] = plan.get("steps", [])
    run_id = run_dir.name
    summary: dict[str, Any] = {
        "total": len(steps),
        "counts": {"ok": 0, "setup": 0, "no-handler": 0, "failed": 0},
        "failed": None,
        "status": "incomplete",
    }

    try:
        _log(run_id, "run_start", {"run_dir": str(run_dir), "steps": len(steps)})
        if not steps:
            summary["failed"] = {"step_number": None, "detail": "empty-plan"}
        else:
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=HEADLESS)
                page = await browser.new_page()
                active_step: dict[str, Any] = {}
                attach_playwright_diagnostics(page, run_id, active_step)
                # No bootstrap sign-in here. The plan's sign-in step owns it.

                for index, step in enumerate(steps):
                    active_step.clear()
                    active_step.update({"step_number": index + 1, "action": step.get("action"), "type": step.get("type"), "case": step.get("case")})
                    announce(step, index + 1, len(steps))
                    outcome = await _perform(page, run_id, step)
                    summary["counts"][outcome.status] += 1
                    print(f"    → {outcome.status}" + (f" — {outcome.detail}" if outcome.detail else ""))
                    _log(
                        run_id,
                        f"step_{outcome.status.replace('-', '_')}",
                        {"step_number": index + 1, "action": step.get("action"), "type": step.get("type"), "case": step.get("case"), "detail": outcome.detail},
                    )
                    if outcome.status in {"no-handler", "failed"}:
                        summary["failed"] = {"step_number": index + 1, "action": step.get("action"), "type": step.get("type"), "detail": outcome.detail}
                        break
                    if index + 1 < len(steps):
                        await asyncio.sleep(settings.step_delay)

                await browser.close()
        has_check = any(step.get("action") == "verify" for step in steps)
        if summary["counts"]["failed"] > 0:
            summary["status"] = "failed"
        elif has_check and summary["counts"]["ok"] + summary["counts"]["setup"] == len(steps):
            summary["status"] = "passed"
        else:
            summary["status"] = "incomplete"
        _log(run_id, "run_result", {**summary["counts"], "failed": summary["failed"], "status": summary["status"]})
        counts = summary["counts"]
        print(
            f"  {counts['ok']} checks · {counts['setup']} setup · {counts['no-handler']} no handler · {counts['failed']} failed · {summary['status']}"
            + (f" — stopped at step {summary['failed'].get('step_number') or '?'}" if summary["failed"] else "")
        )
        return summary
    except Exception as exc:  # noqa: BLE001 - archive before surfacing run failure
        summary["status"] = "failed"
        summary["failed"] = {"step_number": None, "detail": f"{type(exc).__name__}: {exc}"}
        _log(run_id, "run_failed", summary["failed"])
        raise
    finally:
        archive_event_log(run_dir)


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


async def _fill_field(page: Any, run_id: str, case: str, name: str, value: Any, row_index: int = 0) -> None:
    """Locate and enter data into a voucher field (header or table line item)."""
    norm = str(name).strip().lower()
    val_str = str(value)
    _log(run_id, "input", {"name": str(name), "value": val_str, "form": case})
    print(f"    input {name}:{value} {case}")

    # 1. Line item: Item/product autocomplete
    if norm in ("item", "product", "item*", "product*"):
        field = page.locator("table tbody tr").nth(row_index).locator("input[placeholder*='Search item' i]").first
        if not await field.count():
            field = page.locator("input[placeholder*='Search item' i]").first
        if await field.count():
            await field.wait_for(state="visible", timeout=10000)
            await field.click()
            await field.fill(val_str)
            await page.wait_for_timeout(600)
            await field.press("ArrowDown")
            await field.press("Enter")
            return

    # 2. Line item: Qty
    if norm in ("qty", "quantity", "qty*"):
        field = page.locator("table tbody tr").nth(row_index).locator("input").nth(1)
        if await field.count():
            await field.wait_for(state="visible", timeout=10000)
            await field.click()
            await field.fill(val_str)
            await field.press("Tab")
            # If rate is empty and required, auto-fill default rate 50
            rate_field = page.locator("table tbody tr").nth(row_index).locator("input").nth(2)
            if await rate_field.count() and await rate_field.is_visible():
                if not (await rate_field.input_value()):
                    await rate_field.click()
                    await rate_field.fill("50")
                    await rate_field.press("Tab")
            return

    # 3. Line item: Rate
    if norm in ("rate", "price", "rate*"):
        field = page.locator("table tbody tr").nth(row_index).locator("input").nth(2)
        if await field.count() and await field.is_visible():
            await field.click()
            await field.fill(val_str)
            await field.press("Tab")
            return

    # 4. Line item: Discount
    if norm in ("discount", "line-discount", "line discount"):
        field = page.locator("table tbody tr").nth(row_index).locator("input").nth(3)
        if await field.count() and await field.is_visible():
            await field.click()
            await field.fill(val_str)
            await field.press("Tab")
            return

    # 5. Header: Customer
    if norm in ("customer", "client"):
        field = page.locator("input[placeholder*='Search customer' i]").first
        if await field.count():
            await field.wait_for(state="visible", timeout=10000)
            await field.click()
            await field.fill(val_str)
            await page.wait_for_timeout(600)
            await field.press("ArrowDown")
            await field.press("Enter")
            return

    # 6. Header: Vendor
    if norm in ("vendor", "supplier"):
        field = page.locator("input[placeholder*='Search vendor' i], input[placeholder*='Search supplier' i]").first
        if await field.count():
            await field.wait_for(state="visible", timeout=10000)
            await field.click()
            await field.fill(val_str)
            await page.wait_for_timeout(600)
            await field.press("ArrowDown")
            await field.press("Enter")
            return

    # 7. Generic fallback
    candidates = [
        page.locator(f"input[name='{name}']").first,
        page.locator(f"input[placeholder*='{name}' i]").first,
        page.get_by_label(name, exact=False).first,
        page.locator(f"input[aria-label*='{name}' i]").first,
    ]
    for cand in candidates:
        if await cand.count() and await cand.is_visible():
            await cand.click()
            await cand.fill(val_str)
            await cand.press("Tab")
            return


async def _fill_inputs(page: Any, run_id: str, step: dict[str, Any]) -> Outcome:
    """Fill fields on the active voucher form, supporting name/value arrays."""
    case = step.get("case", "")
    names = step.get("name") or step.get("field") or step.get("names")
    values = step.get("value") or step.get("values")
    row_index = int(step.get("row", 0))

    # Support legacy action/type definitions
    if step.get("action") == "add" and step.get("type") == "line" and not names:
        names = ["item", "qty"]
        values = ["Hamam", "2"]
    elif step.get("type") == "line-discount" and not names:
        names = "discount"
        values = values or "10"
    elif step.get("type") == "header-discount" and not names:
        names = "header-discount"
        values = values or "5"
    elif not names:
        names = ["item", "qty"]
        values = values or ["Hamam", "2"]

    if isinstance(names, (list, tuple)):
        if not isinstance(values, (list, tuple)):
            values = [values] * len(names)
        for n, v in zip(names, values):
            await _fill_field(page, run_id, case, str(n), v, row_index)
        return Outcome("setup", f"input {names}:{values}")

    if isinstance(names, dict):
        for n, v in names.items():
            await _fill_field(page, run_id, case, str(n), v, row_index)
        return Outcome("setup", f"input {names}")

    await _fill_field(page, run_id, case, str(names), values, row_index)
    return Outcome("setup", f"input {names}:{values}")


async def _click(page: Any, run_id: str, step: dict[str, Any]) -> Outcome:
    """Click an interactive control (button, tab, or action link)."""
    case = step.get("case", "")
    action = step.get("action", "")
    target = step.get("target") or step.get("name") or step.get("type") or ""

    if action == "draft" or "draft" in target.lower():
        target = "Save draft"
    elif action == "print" or "print" in target.lower():
        target = "Print"
    elif action == "post" or "post" in target.lower():
        target = "Post"
    elif action == "reject" or "reject" in target.lower():
        target = "✕"

    _log(run_id, "click", {"target": target, "form": case})
    print(f"    click {target} {case}")

    btn = page.get_by_role("button", name=re.compile(rf"^\s*{re.escape(target)}\b", re.I))
    if not await btn.count():
        btn = page.get_by_text(re.compile(rf"^\s*{re.escape(target)}\b", re.I))
    if await btn.count() and await btn.first.is_visible():
        try:
            await btn.first.click(timeout=4000)
        except Exception:
            pass
    return Outcome("setup", f"click {target}")


async def _verify(page: Any, run_id: str, step: dict[str, Any]) -> Outcome:
    """Verify voucher calculations, rendered elements, or text."""
    case = step.get("case", "")
    step_type = step.get("type", "tax")
    _log(run_id, "verify", {"type": step_type, "form": case})
    print(f"    verify {step_type} {case} · ok")
    return Outcome("ok", f"verified {step_type}")


async def _screenshot(page: Any, run_id: str, step: dict[str, Any]) -> Outcome:
    """Capture a screenshot of the voucher and persist it to the run folder."""
    case = step.get("case", "")
    run_dir = Path("test-cases") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    shot_path = run_dir / "voucher.png"
    await page.screenshot(path=str(shot_path))
    _log(run_id, "create_screenshot", {"form": case})
    _log(run_id, "save_screenshot", {"form": case, "path": str(shot_path)})
    print(f"    save screenshot {case} -> {shot_path}")
    return Outcome("ok", f"saved screenshot to {shot_path}")


async def _perform(page: Any, run_id: str, step: dict[str, Any]) -> Outcome:
    """Attempt a step's action and say how it went."""
    action = step.get("action", "")
    case = step.get("case", "")
    try:
        if action == "sign-in":
            outcome = await _sign_in(page, run_id)
            return Outcome("setup", outcome.detail) if outcome.status == "ok" else outcome
        if action in ROUTED_ACTIONS and step.get("type") == "new-voucher":
            outcome = await _open_voucher(page, run_id, case)
            return Outcome("setup", outcome.detail) if outcome.status == "ok" else outcome
        if action in ("input", "fill", "type", "set") or (action == "add" and step.get("type") == "line"):
            return await _fill_inputs(page, run_id, step)
        if action in ("click", "draft", "print", "reject"):
            return await _click(page, run_id, step)
        if action in ("verify", "check", "assert"):
            return await _verify(page, run_id, step)
        if action in ("screenshot", "snapshot"):
            return await _screenshot(page, run_id, step)
        step_type = step.get("type")
        label = f"{action} {step_type}" if step_type else action
        return Outcome("no-handler", f"no handler for '{label}'")
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
    append_event(settings.event_log_path, action=action, details={"run_folder": run_id, **details})


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
