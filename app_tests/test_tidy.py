"""Tests for app.tidy — the workspace tidier.

These run against a real temporary filesystem with real symlinks, because the
symlink handling is the part most likely to break and least likely to be
exercised by mocks.
"""

import os
import tempfile
import unittest
from pathlib import Path

from app.tidy import (
    case_folders,
    case_state,
    link_case,
    link_cases,
    prepare,
    render_session,
    tidy_template,
    write_session,
)


class TempTree(unittest.TestCase):
    """Gives each test a repo-shaped tree: runs/ and _template/."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.runs = self.root / "test-cases"
        self.template = self.root / "_template"
        self.runs.mkdir()
        self.template.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_run(self, run_id: str = "002", brief: str = "Work Platform — Test Manual.md") -> Path:
        run_dir = self.runs / run_id
        run_dir.mkdir()
        (run_dir / brief).write_text("# brief\n", encoding="utf-8")
        return run_dir

    def make_case(self, case: str, *, recording: bool = True, url: bool = True) -> Path:
        case_dir = self.template / case
        case_dir.mkdir()
        if recording:
            (case_dir / f"{case}.py").write_text(
                "from playwright.sync_api import sync_playwright\n", encoding="utf-8"
            )
        if url:
            (case_dir / "url.txt").write_text("https://tenant.example/work\n", encoding="utf-8")
        return case_dir


class TidyTemplateTests(TempTree):
    def test_loose_recording_is_moved_into_its_case_folder(self) -> None:
        """The lazy path: the human drops a flat .py into _template/."""
        loose = self.template / "sales-invoice.py"
        loose.write_text("# recorded\n", encoding="utf-8")

        moved = tidy_template(self.template)

        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0]["case"], "sales-invoice")
        self.assertFalse(loose.exists(), "the flat file should be gone")
        self.assertTrue((self.template / "sales-invoice" / "sales-invoice.py").is_file())

    def test_recording_already_in_a_folder_is_left_alone(self) -> None:
        self.make_case("purchase-bill")

        moved = tidy_template(self.template)

        self.assertEqual(moved, [])
        self.assertTrue((self.template / "purchase-bill" / "purchase-bill.py").is_file())

    def test_tidy_is_idempotent(self) -> None:
        (self.template / "effort-hours.py").write_text("# x\n", encoding="utf-8")

        first = tidy_template(self.template)
        second = tidy_template(self.template)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertTrue((self.template / "effort-hours" / "effort-hours.py").is_file())

    def test_tidy_keeps_non_python_files_where_they_are(self) -> None:
        notes = self.template / "README.txt"
        notes.write_text("scratch\n", encoding="utf-8")

        tidy_template(self.template)

        self.assertTrue(notes.is_file())
        self.assertFalse((self.template / "README").exists())

    def test_missing_template_dir_is_not_an_error(self) -> None:
        self.assertEqual(tidy_template(self.root / "nope"), [])


class LinkCaseTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.run_dir = self.make_run()

    def test_link_is_created_pointing_two_levels_up(self) -> None:
        self.make_case("subtasks")

        result = link_case(self.run_dir, self.template, "subtasks")

        self.assertEqual(result, "created")
        link = self.run_dir / "subtasks"
        self.assertTrue(link.is_symlink())
        self.assertEqual(Path(os.readlink(link)), Path("../../_template/subtasks"))
        self.assertTrue(link.is_dir(), "the link should resolve to the case folder")

    def test_linking_twice_changes_nothing(self) -> None:
        self.make_case("attachments")

        self.assertEqual(link_case(self.run_dir, self.template, "attachments"), "created")
        self.assertEqual(link_case(self.run_dir, self.template, "attachments"), "already-linked")

    def test_wrong_target_is_repaired(self) -> None:
        self.make_case("dispatch")
        stale = self.run_dir / "dispatch"
        stale.symlink_to(Path("../../../elsewhere/dispatch"), target_is_directory=True)

        result = link_case(self.run_dir, self.template, "dispatch")

        self.assertEqual(result, "repaired")
        self.assertEqual(Path(os.readlink(stale)), Path("../../_template/dispatch"))

    def test_a_real_directory_is_never_replaced(self) -> None:
        """Something is living where the link belongs. Do not destroy it."""
        squatter = self.run_dir / "reports"
        squatter.mkdir()
        (squatter / "keep.txt").write_text("mine\n", encoding="utf-8")

        result = link_case(self.run_dir, self.template, "reports")

        self.assertEqual(result, "skipped")
        self.assertFalse((self.run_dir / "reports").is_symlink())
        self.assertTrue((squatter / "keep.txt").is_file())

    def test_case_with_no_template_folder_still_gets_a_link(self) -> None:
        result = link_case(self.run_dir, self.template, "not-recorded-yet")

        self.assertEqual(result, "created")
        self.assertTrue((self.run_dir / "not-recorded-yet").is_symlink())
        self.assertFalse((self.run_dir / "not-recorded-yet").exists())

    def test_link_cases_reports_every_case(self) -> None:
        self.make_case("one")
        self.make_case("two")

        report = link_cases(self.run_dir, self.template, ["one", "two", "three"])

        self.assertEqual(report, {"one": "created", "two": "created", "three": "created"})


class CaseStateTests(TempTree):
    def test_case_with_a_recording_is_complete(self) -> None:
        run_dir = self.make_run()
        self.make_case("effort-hours")

        link_case(run_dir, self.template, "effort-hours")

        self.assertEqual(case_state(run_dir, "effort-hours"), "complete")

    def test_case_without_a_recording_is_pending(self) -> None:
        run_dir = self.make_run()
        (self.template / "sla-versions").mkdir()

        link_case(run_dir, self.template, "sla-versions")

        self.assertEqual(case_state(run_dir, "sla-versions"), "pending")

    def test_case_with_nothing_at_all_is_pending(self) -> None:
        run_dir = self.make_run()
        link_case(run_dir, self.template, "ghost")

        self.assertEqual(case_state(run_dir, "ghost"), "pending")


class SessionTests(TempTree):
    def test_session_lists_every_case_with_its_state(self) -> None:
        run_dir = self.make_run()
        self.make_case("done-case")
        self.make_case("todo-case", recording=False)
        link_cases(run_dir, self.template, ["done-case", "todo-case"])

        text = render_session(
            run_dir,
            run_dir / "Work Platform — Test Manual.md",
            ["done-case", "todo-case"],
            self.template,
        )

        self.assertIn("- [x] `done-case` — complete", text)
        self.assertIn("- [ ] `todo-case` — pending", text)

    def test_session_names_the_blocker_when_url_is_missing(self) -> None:
        """Unrecorded and no URL: the human cannot record it yet."""
        run_dir = self.make_run()
        self.make_case("effort-hours", recording=False, url=False)
        link_cases(run_dir, self.template, ["effort-hours"])

        text = render_session(run_dir, None, ["effort-hours"], self.template)

        self.assertIn("Working on: `effort-hours`", text)
        self.assertIn("url.txt", text)
        self.assertIn("do not infer it", text)

    def test_a_recorded_case_is_not_blocked_on_a_url(self) -> None:
        """The recording already carries its URL in page.goto(). Nothing is blocked."""
        run_dir = self.make_run()
        self.make_case("effort-hours", url=False)
        link_cases(run_dir, self.template, ["effort-hours"])

        text = render_session(run_dir, None, ["effort-hours"], self.template)

        self.assertNotIn("Blocked", text)
        self.assertIn("The loop is done for this run", text)

    def test_session_does_not_claim_a_blocker_when_url_exists(self) -> None:
        run_dir = self.make_run()
        self.make_case("effort-hours")
        link_cases(run_dir, self.template, ["effort-hours"])

        text = render_session(run_dir, None, ["effort-hours"], self.template)

        self.assertNotIn("Blocked", text)

    def test_session_reports_done_when_nothing_is_pending(self) -> None:
        run_dir = self.make_run()
        self.make_case("all-done")
        link_cases(run_dir, self.template, ["all-done"])

        text = render_session(run_dir, None, ["all-done"], self.template)

        self.assertIn("The loop is done for this run", text)

    def test_write_session_replaces_rather_than_appends(self) -> None:
        run_dir = self.make_run()
        self.make_case("one")
        link_cases(run_dir, self.template, ["one"])
        write_session(run_dir, None, ["one"], self.template)

        self.make_case("two")
        link_cases(run_dir, self.template, ["one", "two"])
        write_session(run_dir, None, ["one", "two"], self.template)

        text = (run_dir / "session.md").read_text(encoding="utf-8")
        self.assertEqual(text.count("# Run"), 1, "session.md must be rewritten, not appended")


class PrepareTests(TempTree):
    def test_full_pass_tidies_links_and_writes_the_session(self) -> None:
        self.make_run()
        (self.template / "effort-hours.py").write_text("# recorded\n", encoding="utf-8")
        (self.template / "subtasks").mkdir()
        (self.template / "subtasks" / "subtasks.py").write_text("# x\n", encoding="utf-8")

        report = prepare(runs_root=self.runs, template_dir=self.template)

        self.assertEqual(report["action"], "prepared")
        self.assertEqual(report["run_id"], "002")
        self.assertEqual(report["brief"], "Work Platform — Test Manual.md")
        self.assertEqual([t["case"] for t in report["tidied"]], ["effort-hours"])
        self.assertEqual(report["states"]["subtasks"], "complete")
        self.assertTrue((self.runs / "002" / "subtasks").is_symlink())
        self.assertTrue((self.runs / "002" / "session.md").is_file())

    def test_second_pass_is_a_no_op(self) -> None:
        self.make_run()
        self.make_case("subtasks")

        first = prepare(runs_root=self.runs, template_dir=self.template)
        second = prepare(runs_root=self.runs, template_dir=self.template)

        self.assertEqual(first["tidied"], [])
        self.assertEqual(second["tidied"], [])
        self.assertEqual(second["linked"], {"subtasks": "already-linked"})

    def test_dry_run_changes_nothing_on_disk(self) -> None:
        self.make_run()
        (self.template / "lazy.py").write_text("# x\n", encoding="utf-8")

        report = prepare(runs_root=self.runs, template_dir=self.template, dry_run=True)

        self.assertTrue(report["dry_run"])
        self.assertTrue((self.template / "lazy.py").is_file(), "must not move anything")
        self.assertFalse((self.template / "lazy").exists())
        self.assertFalse((self.runs / "002" / "lazy").exists())
        self.assertFalse((self.runs / "002" / "session.md").exists())

    def test_latest_run_wins_over_older_ones(self) -> None:
        self.make_run("001")
        self.make_run("003")
        self.make_case("subtasks")

        report = prepare(runs_root=self.runs, template_dir=self.template)

        self.assertEqual(report["run_id"], "003")
        self.assertTrue((self.runs / "003" / "subtasks").is_symlink())
        self.assertFalse((self.runs / "001" / "subtasks").exists())

    def test_explicit_run_id_overrides_latest(self) -> None:
        self.make_run("001")
        self.make_run("002")
        self.make_case("subtasks")

        report = prepare(runs_root=self.runs, template_dir=self.template, run_id="001")

        self.assertEqual(report["run_id"], "001")
        self.assertTrue((self.runs / "001" / "subtasks").is_symlink())

    def test_explicit_cases_override_discovery(self) -> None:
        self.make_run()
        self.make_case("on-disk")
        self.make_case("named-explicitly")

        report = prepare(
            runs_root=self.runs, template_dir=self.template, cases=["named-explicitly"]
        )

        self.assertEqual(list(report["states"]), ["named-explicitly"])

    def test_missing_run_id_is_reported_not_raised(self) -> None:
        report = prepare(runs_root=self.runs, template_dir=self.template, run_id="099")

        self.assertEqual(report["action"], "no-such-run")

    def test_no_run_folder_at_all_is_reported(self) -> None:
        report = prepare(runs_root=self.runs / "elsewhere", template_dir=self.template)

        self.assertEqual(report["action"], "no-run")

    def test_run_without_a_brief_still_links(self) -> None:
        run_dir = self.runs / "002"
        run_dir.mkdir()
        self.make_case("subtasks")

        report = prepare(runs_root=self.runs, template_dir=self.template)

        self.assertIsNone(report["brief"])
        self.assertTrue((run_dir / "subtasks").is_symlink())

    def test_case_folders_lists_only_real_directories(self) -> None:
        self.make_case("alpha")
        (self.template / "beta.py").write_text("# flat\n", encoding="utf-8")

        self.assertEqual(case_folders(self.template), ["alpha"])


if __name__ == "__main__":
    unittest.main()