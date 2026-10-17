import tempfile
import unittest
from pathlib import Path

from app.loop import HEADLESS, gate
from app.planner import PLAN_FILENAME


def make_run(root: Path, run_id: str = "001", *, brief: bool = True, plan: bool = False) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    if brief:
        (run_dir / "notes.md").write_text("# brief\n", encoding="utf-8")
    if plan:
        (run_dir / PLAN_FILENAME).write_text("<html></html>", encoding="utf-8")
    return run_dir


class GateTests(unittest.TestCase):
    def test_browser_is_never_headless(self) -> None:
        self.assertFalse(HEADLESS)

    def test_run_with_plan_runs_the_browser(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_run(root, plan=True)

            report = gate(root)

            self.assertEqual(report["loop"], "run-browser")
            self.assertEqual(report["run_id"], "001")
            self.assertTrue(report["plan_present"])

    def test_run_without_plan_waits_instead_of_running(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_run(root, plan=False)

            report = gate(root)

            self.assertEqual(report["loop"], "await-plan")
            self.assertIn("AI must create it", report["reason"])

    def test_plan_presence_alone_decides_the_gate(self) -> None:
        """A plan is enough to run, whether or not the brief is there."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_run(root, brief=False, plan=True)

            self.assertEqual(gate(root)["loop"], "run-browser")

    def test_missing_run_stops(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = gate(Path(directory))

            self.assertEqual(report["loop"], "stop")
            self.assertEqual(report["action"], "no-run")

    def test_non_numeric_folders_are_not_a_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "draft").mkdir()
            (root / "draft" / PLAN_FILENAME).write_text("<html></html>", encoding="utf-8")

            self.assertEqual(gate(root)["loop"], "stop")

    def test_gate_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = make_run(root, plan=False)
            before = sorted(path.name for path in run_dir.iterdir())

            gate(root)

            self.assertEqual(sorted(path.name for path in run_dir.iterdir()), before)

    def test_plan_counts_as_present_regardless_of_brief(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_run(root, plan=True)

            self.assertTrue(gate(root)["plan_present"])


if __name__ == "__main__":
    unittest.main()
