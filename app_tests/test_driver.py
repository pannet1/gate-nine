import json
import tempfile
import unittest
from pathlib import Path

from app.driver import HEADLESS, parse_plan, plan_path, route_for


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

    def test_steps_keep_stable_ids_and_order(self) -> None:
        steps = [{"id": str(n), "action": "open-new", "voucher": "Sales Invoice"} for n in (1, 2, 17)]
        with tempfile.TemporaryDirectory() as directory:
            plan = parse_plan(write_plan(directory, steps))

            self.assertEqual([s["id"] for s in plan["steps"]], ["1", "2", "17"])

    # Actions that reach a voucher by navigating to its route. Anything else —
    # sign-in, for instance — has no route by design.
    ROUTED_ACTIONS = {"open-new", "print", "draft-post-correct"}

    def test_every_routed_step_has_a_route(self) -> None:
        """A routed step without a route degrades to label-hunting, silently."""
        real = Path("test-cases/001/test.html")
        if not real.is_file():
            self.skipTest("run 001 not present")
            return
        plan = parse_plan(real)

        unrouted = sorted({
            s["voucher"] for s in plan["steps"]
            if s.get("action") in self.ROUTED_ACTIONS and route_for(s["voucher"]) is None
        })
        self.assertEqual(unrouted, [], f"vouchers with no route: {unrouted}")

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
        """Run 001 ships with the loop — assert it stays parseable."""
        real = Path("test-cases/001/test.html")
        if not real.is_file():
            self.skipTest("run 001 not present")
            return
        plan = parse_plan(real)

        self.assertTrue(plan["steps"], "plan has no steps")
        for step in plan["steps"]:
            for field in ("id", "action", "voucher", "check"):
                self.assertIn(field, step, f"step missing {field}: {step}")


if __name__ == "__main__":
    unittest.main()
