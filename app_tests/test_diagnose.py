import json
import tempfile
import unittest
from pathlib import Path

from app.diagnose import diagnose


def make_run(root: Path, run_id: str = "001", *, plan: bool = True) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    if plan:
        (run_dir / "test.html").write_text("<html></html>", encoding="utf-8")
    return run_dir


class DiagnosisTests(unittest.TestCase):
    def test_no_run_waits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(diagnose(Path(directory))["action"], "no-run")

    def test_plan_without_local_log_is_still_diagnosed(self) -> None:
        """There is no local events.jsonl anymore; a plan present means diagnose."""
        with tempfile.TemporaryDirectory() as directory:
            make_run(Path(directory), plan=True)
            result = diagnose(Path(directory))
            self.assertEqual(result["action"], "diagnose")
            self.assertTrue(result["plan_present"])
            self.assertEqual(result["event_count"], 0)

    def test_local_events_are_not_inspected(self) -> None:
        """Events stream remotely; a leftover local file does not change the gate."""
        with tempfile.TemporaryDirectory() as directory:
            run_dir = make_run(Path(directory))
            (run_dir / "events.jsonl").write_text(
                "".join(
                    json.dumps(event) + "\n"
                    for event in [
                        {"action": "step_no_handler"},
                        {"action": "step_failed"},
                        {"action": "run_failed"},
                        {"action": "playwright_page_error", "details": {"error": "JS error"}},
                    ]
                ),
                encoding="utf-8",
            )
            result = diagnose(Path(directory))
            self.assertEqual(result["action"], "diagnose")
            self.assertEqual(result["harness_gaps"], [])
            self.assertEqual(result["failed_steps"], [])
            self.assertEqual(result["run_failures"], [])
            self.assertEqual(result["playwright_errors"], [])
            self.assertFalse(result["human_browser_review_required"])
            self.assertEqual(result["product_bug_status"], "undetermined")

    def test_highest_run_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            make_run(Path(directory), "001", plan=True)
            make_run(Path(directory), "002", plan=False)
            result = diagnose(Path(directory))
            self.assertEqual(result["run_id"], "002")
            self.assertEqual(result["action"], "await-plan")


if __name__ == "__main__":
    unittest.main()
