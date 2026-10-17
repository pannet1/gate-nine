import json
import tempfile
import unittest
from pathlib import Path

from app.diagnose import diagnose


def make_run(root: Path, run_id: str = "001", *, plan: bool = True, log: list[dict] | None = None) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    if plan:
        (run_dir / "test.html").write_text("<html></html>", encoding="utf-8")
    if log is not None:
        (run_dir / "events.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in log), encoding="utf-8"
        )
    return run_dir


class DiagnosisTests(unittest.TestCase):
    def test_no_run_waits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(diagnose(Path(directory))["action"], "no-run")

    def test_plan_without_archived_log_waits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            make_run(Path(directory), plan=True)
            result = diagnose(Path(directory))
            self.assertEqual(result["action"], "await-log")

    def test_both_files_enable_diagnosis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            make_run(
                Path(directory),
                log=[
                    {"action": "step_no_handler"},
                    {"action": "step_failed"},
                    {"action": "run_failed"},
                    {"action": "playwright_page_error", "details": {"error": "JS error"}},
                ],
            )
            result = diagnose(Path(directory))
            self.assertEqual(result["action"], "diagnose")
            self.assertEqual(len(result["harness_gaps"]), 1)
            self.assertTrue(result["human_browser_review_required"])
            self.assertTrue(result["developer_review_required"])
            self.assertEqual(len(result["playwright_errors"]), 1)
            self.assertEqual(result["product_bug_status"], "undetermined")

    def test_highest_run_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            make_run(Path(directory), "001", log=[])
            make_run(Path(directory), "002", plan=False)
            result = diagnose(Path(directory))
            self.assertEqual(result["run_id"], "002")
            self.assertEqual(result["action"], "await-plan")


if __name__ == "__main__":
    unittest.main()
