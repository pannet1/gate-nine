import tempfile
import unittest
from pathlib import Path

from app.planner import (
    PLAN_FILENAME,
    discover,
    find_brief,
    find_latest_run,
    list_case_folders,
)


def make_run(root: Path, run_id: str, *, brief: str | None = None, cases: tuple[str, ...] = ()) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    if brief is not None:
        (run_dir / brief).write_text("# brief\n", encoding="utf-8")
    for case in cases:
        (run_dir / case).mkdir()
    return run_dir


class RunDiscoveryTests(unittest.TestCase):
    def test_latest_run_is_highest_numbered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for run_id in ("002", "010", "001"):
                make_run(root, run_id)
            (root / "notes").mkdir()

            self.assertEqual(find_latest_run(root).name, "010")

    def test_run_names_that_are_not_numbers_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_run(root, "draft-run")

            self.assertIsNone(find_latest_run(root))

    def test_missing_root_is_not_a_run(self) -> None:
        self.assertIsNone(find_latest_run(Path("/nonexistent/runs")))


class BriefDiscoveryTests(unittest.TestCase):
    def test_brief_is_found_regardless_of_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = make_run(Path(directory), "001", brief="murugesan-anything.MD")

            self.assertEqual([brief.name for brief in find_brief(run_dir)], ["murugesan-anything.MD"])

    def test_only_markdown_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "001"
            run_dir.mkdir()
            (run_dir / "notes.txt").write_text("x", encoding="utf-8")
            (run_dir / PLAN_FILENAME).write_text("<html></html>", encoding="utf-8")

            self.assertEqual(find_brief(run_dir), [])


class DiscoveryReportTests(unittest.TestCase):
    def test_brief_found_reports_run_and_brief(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_run(root, "001", brief="notes.md", cases=("goods-receipt", "credit-note"))

            result = discover(root)

            self.assertEqual(result["action"], "brief-found")
            self.assertEqual(result["run_id"], "001")
            self.assertEqual(result["brief"], "notes.md")
            self.assertEqual(result["case_folders"], ["credit-note", "goods-receipt"])
            self.assertFalse(result["plan_present"])

    def test_plan_presence_is_reported_not_created(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = make_run(root, "001", brief="notes.md")
            (run_dir / PLAN_FILENAME).write_text("HAND-WRITTEN", encoding="utf-8")

            result = discover(root)

            self.assertTrue(result["plan_present"])
            self.assertEqual((run_dir / PLAN_FILENAME).read_text(encoding="utf-8"), "HAND-WRITTEN")

    def test_no_brief_is_reported_and_nothing_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_run(root, "001", cases=("goods-receipt",))

            result = discover(root)

            self.assertEqual(result["action"], "no-brief")
            self.assertNotIn("brief", result)
            self.assertFalse((root / "001" / PLAN_FILENAME).exists())

    def test_discovery_never_writes_a_plan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_run(root, "001", brief="notes.md", cases=("goods-receipt",))
            before = sorted(path.name for path in (root / "001").iterdir())

            discover(root)

            after = sorted(path.name for path in (root / "001").iterdir())
            self.assertEqual(before, after)

    def test_empty_root_reports_no_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = discover(Path(directory))

            self.assertEqual(result["action"], "no-run")

    def test_multiple_briefs_are_flagged_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = make_run(root, "001", brief="a.md")
            (run_dir / "b.md").write_text("# b\n", encoding="utf-8")

            result = discover(root)

            self.assertEqual(result["action"], "brief-found")
            self.assertTrue(result["ambiguous"])
            self.assertEqual(result["brief"], "a.md")

    def test_case_folders_reported_separately_from_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = make_run(Path(directory), "001", brief="notes.md", cases=("goods-receipt",))
            (run_dir / "loose-file.md").write_text("x", encoding="utf-8")

            self.assertEqual([folder.name for folder in list_case_folders(run_dir)], ["goods-receipt"])


if __name__ == "__main__":
    unittest.main()
