import json
import tempfile
import unittest
from pathlib import Path

from app.driver import (
    HEADLESS,
    ROUTED_ACTIONS,
    archive_event_log,
    parse_plan,
    plan_path,
    prepare_event_log,
    route_for,
)


def write_plan(directory: str, steps: list[dict] | None = None, *, with_block: bool = True, run_id: str = "001") -> Path:
    path = Path(directory) / "test.html"
    payload = {"run_id": run_id, "steps": steps if steps is not None else [{"id": "1", "action": "open-new", "voucher": "Sales Invoice"}]}
    block = f'<script type="application/json" id="plan">\n{json.dumps(payload)}\n</script>' if with_block else ""
    path.write_text(f"<!DOCTYPE html>\n<html><body>\n<h1>Plan</h1>\n<table><tr><td>prose for humans</td></tr></table>\n{block}\n</body></html>", encoding="utf-8")
    return path


class PlanParsingTests(unittest.TestCase):
    def test_browser_is_never_headless(self) -> None:
        self.assertFalse(HEADLESS)

    def test_reads_json_block_from_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan = parse_plan(write_plan(directory, run_id="042"))

            self.assertEqual(plan["run_id"], "042")
            self.assertEqual(plan["steps"][0]["voucher"], "Sales Invoice")

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

    def test_event_log_archive_cannot_overwrite_existing_run_log(self) -> None:
        from app.config import settings

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "001"
            run_dir.mkdir()
            (run_dir / "events.jsonl").write_text("old\n", encoding="utf-8")
            original = settings.event_log_path
            settings.event_log_path = root / "events.jsonl"
            try:
                with self.assertRaises(FileExistsError):
                    prepare_event_log(run_dir)
            finally:
                settings.event_log_path = original

    def test_steps_keep_stable_ids_and_order(self) -> None:
        steps = [{"id": str(n), "action": "open-new", "voucher": "Sales Invoice"} for n in (1, 2, 17)]
        with tempfile.TemporaryDirectory() as directory:
            plan = parse_plan(write_plan(directory, steps))

            self.assertEqual([s["id"] for s in plan["steps"]], ["1", "2", "17"])

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

        allowed = {"id", "phase", "test", "action", "case"}
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
        self.assertEqual(first["id"], "0")

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
            for field in ("id", "action", "case"):
                self.assertIn(field, step, f"step missing {field}: {step}")


class UnattendedRunTests(unittest.TestCase):
    """The runner must not wait for a keystroke — eyes watch, code drives."""

    def test_driver_has_no_interactive_prompt(self) -> None:
        import inspect

        from app import driver

        self.assertFalse(hasattr(driver, "prompt"), "prompting is gone; drive() runs the whole plan")
        self.assertNotIn("input(", inspect.getsource(driver), "no step may block on stdin")


if __name__ == "__main__":
    unittest.main()
