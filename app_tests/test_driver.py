import json
import tempfile
import unittest
from pathlib import Path

from app.driver import (
    HEADLESS,
    ROUTED_ACTIONS,
    archive_event_log,
    attach_playwright_diagnostics,
    parse_plan,
    plan_path,
    prepare_event_log,
    route_for,
)
from app.events import read_events


def write_plan(directory: str, steps: list[dict] | None = None, *, with_block: bool = True) -> Path:
    path = Path(directory) / "test.html"
    payload = {"steps": steps if steps is not None else [{"action": "open", "type": "new-voucher", "case": "sales-invoice"}]}
    block = f'<script type="application/json" id="plan">\n{json.dumps(payload)}\n</script>' if with_block else ""
    path.write_text(f"<!DOCTYPE html>\n<html><body>\n<h1>Plan</h1>\n<table><tr><td>prose for humans</td></tr></table>\n{block}\n</body></html>", encoding="utf-8")
    return path


class PlanParsingTests(unittest.TestCase):
    def test_browser_is_never_headless(self) -> None:
        self.assertFalse(HEADLESS)

    def test_reads_json_block_from_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = parse_plan(write_plan(directory))

            self.assertEqual(plan["steps"][0]["case"], "sales-invoice")

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            parse_plan(Path("/nonexistent/test.html"))

    def test_html_without_plan_block_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                parse_plan(write_plan(directory, with_block=False))

    def test_plan_script_can_start_at_beginning_of_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.html"
            path.write_text(
                '<script type="application/json" id="plan">'
                + json.dumps({"run_id": "001", "steps": []})
                + "</script>",
                encoding="utf-8",
            )

            self.assertEqual(parse_plan(path)["steps"], [])

    def test_ignores_prose_tables_around_the_block(self) -> None:
        """The human tables must not be mistaken for the plan."""
        with tempfile.TemporaryDirectory() as directory:
            plan = parse_plan(write_plan(directory))

            self.assertEqual(len(plan["steps"]), 1)

    def test_plan_path_points_at_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "001"
            run_dir.mkdir()
            self.assertEqual(plan_path(run_dir), run_dir / "test.html")

    def test_event_log_is_created_at_root_and_archived_in_run(self) -> None:
        from app.config import settings

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "001"
            run_dir.mkdir()
            original = settings.event_log_path
            settings.event_log_path = root / "events.jsonl"
            try:
                active = prepare_event_log(run_dir)
                self.assertEqual(active, root / "events.jsonl")
                self.assertTrue(active.is_file())
                self.assertEqual(active.read_text(encoding="utf-8"), "")

                active.write_text('{"action":"run_start"}\n', encoding="utf-8")
                archived = archive_event_log(run_dir)

                self.assertEqual(archived, run_dir / "events.jsonl")
                self.assertFalse(active.exists())
                self.assertEqual(archived.read_text(encoding="utf-8"), '{"action":"run_start"}\n')
            finally:
                settings.event_log_path = original

    def test_event_log_archive_overwrites_existing_run_log(self) -> None:
        from app.config import settings

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "001"
            run_dir.mkdir()
            (run_dir / "events.jsonl").write_text("old\n", encoding="utf-8")
            original = settings.event_log_path
            settings.event_log_path = root / "events.jsonl"
            try:
                active = prepare_event_log(run_dir)
                self.assertEqual(active.read_text(encoding="utf-8"), "")

                active.write_text("new\n", encoding="utf-8")
                archived = archive_event_log(run_dir)
                self.assertEqual(archived.read_text(encoding="utf-8"), "new\n")
            finally:
                settings.event_log_path = original

    def test_playwright_diagnostics_are_logged_with_active_step_context(self) -> None:
        from app.config import settings

        class Emitter:
            def __init__(self) -> None:
                self.handlers = {}

            def on(self, event: str, handler) -> None:
                self.handlers[event] = handler

        class ConsoleMessage:
            type = "error"
            text = "uncaught application error"

        class Request:
            url = "https://tenant.example/path?token=secret#fragment"
            method = "GET"
            resource_type = "fetch"
            failure = "net::ERR_FAILED"

        with tempfile.TemporaryDirectory() as directory:
            original = settings.event_log_path
            settings.event_log_path = Path(directory) / "events.jsonl"
            context = {"step_number": 4, "action": "open", "type": "new-voucher", "case": "sales-invoice"}
            page = Emitter()
            try:
                attach_playwright_diagnostics(page, "001", context)
                page.handlers["console"](ConsoleMessage())
                page.handlers["pageerror"](RuntimeError("uncaught page exception"))
                page.handlers["requestfailed"](Request())
                page.handlers["crash"]()

                events = read_events(settings.event_log_path)
                self.assertEqual(
                    [event["action"] for event in events],
                    [
                        "playwright_console_error",
                        "playwright_page_error",
                        "playwright_request_failed",
                        "playwright_page_crash",
                    ],
                )
                self.assertEqual(events[0]["details"]["step_number"], 4)
                self.assertEqual(events[2]["details"]["url"], "https://tenant.example/path")
                self.assertNotIn("secret", events[2]["details"]["url"])
            finally:
                settings.event_log_path = original

    def test_steps_need_no_authored_ids(self) -> None:
        steps = [{"action": "open", "type": "new-voucher", "case": "sales-invoice"} for _ in range(3)]
        with tempfile.TemporaryDirectory() as directory:
            plan = parse_plan(write_plan(directory, steps))

            self.assertTrue(all("id" not in step for step in plan["steps"]))

    # Anything else — sign-in, for instance — has no route by design.
    def test_every_routed_step_has_a_route(self) -> None:
        """A routed step without a route degrades to label-hunting, silently."""
        real = Path("test-cases/001/test.html")
        if not real.is_file():
            self.skipTest("run 001 not present")
            return
        plan = parse_plan(real)

        unrouted = sorted({
            s["case"] for s in plan["steps"]
            if s.get("action") in ROUTED_ACTIONS and route_for(s["case"]) is None
        })
        self.assertEqual(unrouted, [], f"cases with no route: {unrouted}")

    def test_plan_carries_order_and_no_method(self) -> None:
        """The plan orders the cases; the cases hold the method.

        A step must not grow a check or expected-result field — that is the
        how-to-test, and it lives in app/vouchers/<case>/test-case.html only.
        """
        real = Path("test-cases/001/test.html")
        if not real.is_file():
            self.skipTest("run 001 not present")
            return
        plan = parse_plan(real)

        allowed = {"phase", "test", "action", "type", "case", "name", "value", "target"}
        for step in plan["steps"]:
            with self.subTest(step=step.get("id")):
                extra = set(step) - allowed
                self.assertEqual(
                    extra, set(),
                    f"step carries method fields, which belong to the case: {sorted(extra)}",
                )

    def test_plan_opens_with_sign_in(self) -> None:
        """Every run begins at the login form, before any voucher is touched."""
        real = Path("test-cases/001/test.html")
        if not real.is_file():
            self.skipTest("run 001 not present")
            return
        plan = parse_plan(real)

        first = plan["steps"][0]
        self.assertEqual(first["action"], "sign-in")
        self.assertEqual(first["action"], "sign-in")

    def test_routes_are_new_voucher_forms(self) -> None:
        for name in ("Sales Invoice", "Purchase Bill", "GRN", "Credit Note", "Debit Note"):
            with self.subTest(voucher=name):
                route = route_for(name)
                self.assertIsNotNone(route)
                self.assertTrue(route.endswith("/new/"), f"{name} must open a blank voucher: {route}")

    def test_route_lookup_ignores_case_and_spacing(self) -> None:
        self.assertEqual(route_for("  sales   INVOICE "), route_for("Sales Invoice"))

    def test_grn_and_goods_receipt_share_one_route(self) -> None:
        """The plan says GRN; the tenant's own heading says Goods Receipt."""
        self.assertEqual(route_for("GRN"), route_for("Goods Receipt"))

    def test_unknown_voucher_has_no_route(self) -> None:
        self.assertIsNone(route_for("Vendor Payment"))

    def test_real_run_plan_is_well_formed(self) -> None:
        """Run 001 ships with the driver — assert it stays parseable."""
        real = Path("test-cases/001/test.html")
        if not real.is_file():
            self.skipTest("run 001 not present")
            return
        plan = parse_plan(real)

        self.assertTrue(plan["steps"], "plan has no steps")
        for step in plan["steps"]:
            for field in ("action", "case"):
                self.assertIn(field, step, f"step missing {field}: {step}")


class UnattendedRunTests(unittest.TestCase):
    """The runner must not wait for a keystroke — eyes watch, code drives."""

    def test_driver_has_no_interactive_prompt(self) -> None:
        import inspect

        from app import driver

        self.assertFalse(hasattr(driver, "prompt"), "prompting is gone; drive() runs the whole plan")
        self.assertNotIn("input(", inspect.getsource(driver), "no step may block on stdin")

    def test_perform_distinguishes_setup_from_unsupported(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.driver import Outcome, _perform

        mock_page = MagicMock()
        with patch("app.driver._sign_in", new_callable=AsyncMock) as mock_sign_in, \
             patch("app.driver._open_voucher", new_callable=AsyncMock) as mock_open, \
             patch("app.driver._fill_inputs", new_callable=AsyncMock) as mock_fill_inputs, \
             patch("app.driver._verify", new_callable=AsyncMock) as mock_verify:
            mock_sign_in.return_value = Outcome("ok", "signed in")
            mock_open.return_value = Outcome("ok", "opened")
            mock_fill_inputs.return_value = Outcome("setup", "input ok")
            mock_verify.return_value = Outcome("ok", "verified")

            res1 = asyncio.run(_perform(mock_page, "001", {"action": "sign-in", "case": "login"}))
            self.assertEqual(res1.status, "setup")

            res2 = asyncio.run(_perform(mock_page, "001", {"action": "open", "type": "new-voucher", "case": "sales-invoice"}))
            self.assertEqual(res2.status, "setup")

            res3 = asyncio.run(_perform(mock_page, "001", {"action": "input", "name": ["item", "qty"], "value": ["Hamam", "2"], "case": "sales-invoice"}))
            self.assertEqual(res3.status, "setup")

            res4 = asyncio.run(_perform(mock_page, "001", {"action": "verify", "type": "tax", "case": "sales-invoice"}))
            self.assertEqual(res4.status, "ok")

            res5 = asyncio.run(_perform(mock_page, "001", {"action": "custom"}))
            self.assertEqual(res5.status, "no-handler")
            self.assertEqual(res5.detail, "no handler for 'custom'")

    def test_drive_stops_at_first_unsupported_action(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.config import settings
        from app.driver import Outcome, drive

        steps = [
            {"action": "open", "type": "new-voucher", "case": "sales-invoice"},
            {"action": "custom-unsupported", "case": "sales-invoice"},
            {"action": "print", "type": "voucher", "case": "sales-invoice"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "002"
            run_dir.mkdir()
            write_plan(str(run_dir), steps)
            orig_log = settings.event_log_path
            orig_delay = settings.step_delay
            settings.event_log_path = Path(directory) / "events.jsonl"
            settings.step_delay = 0.0

            mock_page = MagicMock()
            mock_page.on = MagicMock()
            mock_browser = MagicMock()
            mock_browser.new_page = AsyncMock(return_value=mock_page)
            mock_browser.close = AsyncMock()
            mock_playwright = MagicMock()
            mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

            class MockAsyncPlaywrightContext:
                async def __aenter__(self):
                    return mock_playwright

                async def __aexit__(self, *args):
                    pass

            try:
                with patch("playwright.async_api.async_playwright", return_value=MockAsyncPlaywrightContext()), \
                     patch("app.driver._open_voucher", new_callable=AsyncMock) as mock_open:
                    mock_open.return_value = Outcome("ok", "")
                    summary = asyncio.run(drive(run_dir))

                self.assertEqual(summary["status"], "incomplete")
                self.assertEqual(summary["counts"]["setup"], 1)
                self.assertEqual(summary["counts"]["no-handler"], 1)
                self.assertEqual(summary["counts"]["ok"], 0)
                self.assertEqual(summary["counts"]["failed"], 0)
                self.assertEqual(summary["failed"]["step_number"], 2)
                self.assertEqual(summary["failed"]["action"], "custom-unsupported")

                archived = run_dir / "events.jsonl"
                self.assertTrue(archived.exists())
                events = read_events(archived)
                actions = [e["action"] for e in events]
                self.assertIn("run_start", actions)
                self.assertIn("step_setup", actions)
                self.assertIn("step_no_handler", actions)
                self.assertIn("run_result", actions)
                # Verify step 3 was NOT executed
                step_numbers = [e["details"].get("step_number") for e in events if "step_number" in e.get("details", {})]
                self.assertEqual(step_numbers, [1, 2])
            finally:
                settings.event_log_path = orig_log
                settings.step_delay = orig_delay

    def test_drive_stops_on_step_failure(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.config import settings
        from app.driver import Outcome, drive

        steps = [
            {"action": "open", "type": "new-voucher", "case": "sales-invoice"},
            {"action": "open", "type": "new-voucher", "case": "purchase-bill"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "003"
            run_dir.mkdir()
            write_plan(str(run_dir), steps)
            orig_log = settings.event_log_path
            orig_delay = settings.step_delay
            settings.event_log_path = Path(directory) / "events.jsonl"
            settings.step_delay = 0.0

            mock_page = MagicMock()
            mock_page.on = MagicMock()
            mock_browser = MagicMock()
            mock_browser.new_page = AsyncMock(return_value=mock_page)
            mock_browser.close = AsyncMock()
            mock_playwright = MagicMock()
            mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

            class MockAsyncPlaywrightContext:
                async def __aenter__(self):
                    return mock_playwright

                async def __aexit__(self, *args):
                    pass

            try:
                with patch("playwright.async_api.async_playwright", return_value=MockAsyncPlaywrightContext()), \
                     patch("app.driver._open_voucher", new_callable=AsyncMock) as mock_open:
                    mock_open.side_effect = [Outcome("ok", ""), Outcome("failed", "element not found")]
                    summary = asyncio.run(drive(run_dir))

                self.assertEqual(summary["status"], "failed")
                self.assertEqual(summary["counts"]["setup"], 1)
                self.assertEqual(summary["counts"]["failed"], 1)
                self.assertEqual(summary["failed"]["step_number"], 2)

                archived = run_dir / "events.jsonl"
                self.assertTrue(archived.exists())
                events = read_events(archived)
                actions = [e["action"] for e in events]
                self.assertIn("step_failed", actions)
                self.assertIn("run_result", actions)
            finally:
                settings.event_log_path = orig_log
                settings.step_delay = orig_delay

    def test_input_with_name_array_calls_fill_field(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.driver import _fill_inputs

        mock_page = MagicMock()
        with patch("app.driver._fill_field", new_callable=AsyncMock) as mock_fill:
            step = {
                "action": "input",
                "name": ["item", "qty"],
                "value": ["Hamam", "2"],
                "case": "sales-invoice",
            }
            outcome = asyncio.run(_fill_inputs(mock_page, "001", step))
            self.assertEqual(outcome.status, "setup")
            self.assertEqual(mock_fill.call_count, 2)
            mock_fill.assert_any_call(mock_page, "001", "sales-invoice", "item", "Hamam", 0)
            mock_fill.assert_any_call(mock_page, "001", "sales-invoice", "qty", "2", 0)

    def test_input_regular_single_field(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.driver import _fill_inputs

        mock_page = MagicMock()
        with patch("app.driver._fill_field", new_callable=AsyncMock) as mock_fill:
            step = {
                "action": "input",
                "name": "customer",
                "value": "Walk-in",
                "case": "sales-invoice",
            }
            outcome = asyncio.run(_fill_inputs(mock_page, "001", step))
            self.assertEqual(outcome.status, "setup")
            mock_fill.assert_called_once_with(mock_page, "001", "sales-invoice", "customer", "Walk-in", 0)


if __name__ == "__main__":
    unittest.main()
