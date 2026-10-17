import json
import tempfile
import unittest
from pathlib import Path

from app.driver import (
    HEADLESS,
    ROUTED_ACTIONS,
    Outcome,
    parse_plan,
    plan_path,
    render_result,
    result_path,
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

    def test_result_lands_in_the_gitignored_artifacts_dir(self) -> None:
        """A result quotes tenant data, so it must not be committable."""
        self.assertEqual(result_path("001"), Path("artifacts/001-result.txt"))

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
        """Run 001 ships with the loop — assert it stays parseable."""
        real = Path("test-cases/001/test.html")
        if not real.is_file():
            self.skipTest("run 001 not present")
            return
        plan = parse_plan(real)

        self.assertTrue(plan["steps"], "plan has no steps")
        for step in plan["steps"]:
            for field in ("id", "action", "case"):
                self.assertIn(field, step, f"step missing {field}: {step}")


class ResultRenderingTests(unittest.TestCase):
    """A run leaves a text record of what it did and where it stopped."""

    STEPS = [
        {"id": "0", "action": "sign-in", "case": "login"},
        {"id": "1", "action": "open-new", "case": "sales-invoice"},
        {"id": "2", "action": "add-line", "case": "sales-invoice"},
    ]

    @staticmethod
    def summary(**overrides) -> dict:
        base = {
            "run_id": "001",
            "total": 3,
            "started": "2026-10-17T00:00:00",
            "counts": {"ok": 0, "no-handler": 0, "failed": 0},
            "failed": None,
            "result_file": "artifacts/001-result.txt",
        }
        base.update(overrides)
        return base

    def render(self, seen: list, **overrides) -> str:
        return render_result(Path("test-cases/001/test.html"), self.STEPS, seen, self.summary(**overrides))

    def test_steps_not_run_are_named_not_omitted(self) -> None:
        text = self.render([(self.STEPS[0], Outcome("ok"))], counts={"ok": 1, "no-handler": 0, "failed": 0})

        self.assertIn("not reached", text)
        self.assertIn("step 2", text)

    def test_a_failure_stops_the_run_and_is_named(self) -> None:
        seen = [(self.STEPS[0], Outcome("ok")), (self.STEPS[1], Outcome("failed", "no heading"))]
        text = self.render(
            seen,
            counts={"ok": 1, "no-handler": 0, "failed": 1},
            failed={"step": "1", "detail": "no heading"},
        )

        self.assertIn("stopped at step 1 — no heading", text)
        self.assertIn("not reached", text)

    def test_no_handler_is_a_gap_not_a_failure(self) -> None:
        seen = [
            (self.STEPS[0], Outcome("ok")),
            (self.STEPS[1], Outcome("ok")),
            (self.STEPS[2], Outcome("no-handler", "no handler for action 'add-line'")),
        ]
        text = self.render(seen, counts={"ok": 2, "no-handler": 1, "failed": 0})

        self.assertIn("finished every step", text)
        self.assertIn("2 ok · 1 no handler · 0 failed", text)

    def test_empty_plan_says_so(self) -> None:
        text = render_result(Path("test.html"), [], [], self.summary(total=0))

        self.assertIn("no steps in the plan", text)


class UnattendedRunTests(unittest.TestCase):
    """The runner must not wait for a keystroke — eyes watch, code drives."""

    def test_driver_has_no_interactive_prompt(self) -> None:
        import inspect

        from app import driver

        self.assertFalse(hasattr(driver, "prompt"), "prompting is gone; drive() runs the whole plan")
        self.assertNotIn("input(", inspect.getsource(driver), "no step may block on stdin")


if __name__ == "__main__":
    unittest.main()
