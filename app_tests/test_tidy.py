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
    AUTH_RELATIVE,
    case_folders,
    normalise_recordings,
    point_recording_at_auth,
    case_state,
    link_case,
    link_system_auth,
    link_cases,
    prepare,
    render_session,
    tidy_recordings,
    write_session,
)


class TempTree(unittest.TestCase):
    """Gives each test a repo-shaped tree: runs/ and recordings/."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.runs = self.root / "test-cases"
        self.recordings = self.root / "recordings"
        self.runs.mkdir()
        self.recordings.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_run(self, run_id: str = "002", brief: str = "Work Platform — Test Manual.md") -> Path:
        run_dir = self.runs / run_id
        run_dir.mkdir()
        (run_dir / brief).write_text("# brief\n", encoding="utf-8")
        return run_dir

    def make_case(self, case: str, *, recording: bool = True, url: bool = True) -> Path:
        case_dir = self.recordings / case
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
        """The lazy path: the human drops a flat .py into recordings/."""
        loose = self.recordings / "sales-invoice.py"
        loose.write_text("# recorded\n", encoding="utf-8")

        moved = tidy_recordings(self.recordings)

        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0]["case"], "sales-invoice")
        self.assertFalse(loose.exists(), "the flat file should be gone")
        self.assertTrue((self.recordings / "sales-invoice" / "sales-invoice.py").is_file())

    def test_recording_already_in_a_folder_is_left_alone(self) -> None:
        self.make_case("purchase-bill")

        moved = tidy_recordings(self.recordings)

        self.assertEqual(moved, [])
        self.assertTrue((self.recordings / "purchase-bill" / "purchase-bill.py").is_file())

    def test_tidy_is_idempotent(self) -> None:
        (self.recordings / "effort-hours.py").write_text("# x\n", encoding="utf-8")

        first = tidy_recordings(self.recordings)
        second = tidy_recordings(self.recordings)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertTrue((self.recordings / "effort-hours" / "effort-hours.py").is_file())

    def test_tidy_keeps_non_python_files_where_they_are(self) -> None:
        notes = self.recordings / "README.txt"
        notes.write_text("scratch\n", encoding="utf-8")

        tidy_recordings(self.recordings)

        self.assertTrue(notes.is_file())
        self.assertFalse((self.recordings / "README").exists())

    def test_missingrecordings_dir_is_not_an_error(self) -> None:
        self.assertEqual(tidy_recordings(self.root / "nope"), [])


class NormaliseRecordingTests(TempTree):
    """A recording whose name drifted from its folder is renamed to match."""

    def test_drifted_name_is_renamed_to_match_the_folder(self) -> None:
        case_dir = self.make_case("effort-hours")
        (case_dir / "effort-hours.py").rename(case_dir / "effort-hour.py")

        fixed = normalise_recordings(self.recordings)

        self.assertEqual(len(fixed), 1)
        self.assertEqual(fixed[0]["case"], "effort-hours")
        self.assertTrue((case_dir / "effort-hours.py").is_file())
        self.assertFalse((case_dir / "effort-hour.py").exists())

    def test_correctly_named_recording_is_left_alone(self) -> None:
        self.make_case("effort-hours")

        self.assertEqual(normalise_recordings(self.recordings), [])

    def test_two_recordings_are_ambiguous_and_left_alone(self) -> None:
        case_dir = self.make_case("effort-hours")
        (case_dir / "effort-hours.py").rename(case_dir / "effort-hour.py")
        (case_dir / "other.py").write_text("# another\n", encoding="utf-8")

        fixed = normalise_recordings(self.recordings)

        self.assertEqual(len(fixed[0]["ambiguous"]), 2)
        self.assertTrue((case_dir / "effort-hour.py").is_file(), "nothing may be renamed")
        self.assertTrue((case_dir / "other.py").is_file())

    def test_empty_case_folder_is_untouched(self) -> None:
        (self.recordings / "not-recorded-yet").mkdir()

        self.assertEqual(normalise_recordings(self.recordings), [])

    def test_drifted_case_counts_as_complete_after_the_fix(self) -> None:
        """The bug this prevents: a drifted name left the case pending forever."""
        run_dir = self.make_run()
        case_dir = self.make_case("effort-hours")
        (case_dir / "effort-hours.py").rename(case_dir / "effort-hour.py")
        link_case(run_dir, self.recordings, "effort-hours")

        self.assertEqual(case_state(run_dir, "effort-hours"), "pending")

        prepare(runs_root=self.runs, recordings_dir=self.recordings)

        self.assertEqual(case_state(run_dir, "effort-hours"), "complete")


class LinkCaseTests(TempTree):
    def setUp(self) -> None:
        super().setUp()
        self.run_dir = self.make_run()

    def test_link_is_created_pointing_two_levels_up(self) -> None:
        self.make_case("subtasks")

        result = link_case(self.run_dir, self.recordings, "subtasks")

        self.assertEqual(result, "created")
        link = self.run_dir / "subtasks"
        self.assertTrue(link.is_symlink())
        self.assertEqual(Path(os.readlink(link)), Path("../../recordings/subtasks"))
        self.assertTrue(link.is_dir(), "the link should resolve to the case folder")

    def test_linking_twice_changes_nothing(self) -> None:
        self.make_case("attachments")

        self.assertEqual(link_case(self.run_dir, self.recordings, "attachments"), "created")
        self.assertEqual(link_case(self.run_dir, self.recordings, "attachments"), "already-linked")

    def test_wrong_target_is_repaired(self) -> None:
        self.make_case("dispatch")
        stale = self.run_dir / "dispatch"
        stale.symlink_to(Path("../../../elsewhere/dispatch"), target_is_directory=True)

        result = link_case(self.run_dir, self.recordings, "dispatch")

        self.assertEqual(result, "repaired")
        self.assertEqual(Path(os.readlink(stale)), Path("../../recordings/dispatch"))

    def test_a_real_directory_is_never_replaced(self) -> None:
        """Something is living where the link belongs. Do not destroy it."""
        squatter = self.run_dir / "reports"
        squatter.mkdir()
        (squatter / "keep.txt").write_text("mine\n", encoding="utf-8")

        result = link_case(self.run_dir, self.recordings, "reports")

        self.assertEqual(result, "skipped")
        self.assertFalse((self.run_dir / "reports").is_symlink())
        self.assertTrue((squatter / "keep.txt").is_file())

    def test_case_with_norecordings_folder_still_gets_a_link(self) -> None:
        result = link_case(self.run_dir, self.recordings, "not-recorded-yet")

        self.assertEqual(result, "created")
        self.assertTrue((self.run_dir / "not-recorded-yet").is_symlink())
        self.assertFalse((self.run_dir / "not-recorded-yet").exists())

    def test_link_cases_reports_every_case_and_its_auth(self) -> None:
        (self.runs / "auth.json").write_text("{}", encoding="utf-8")
        self.make_case("one")
        self.make_case("two")

        report = link_cases(self.run_dir, self.recordings, ["one", "two", "three"])

        self.assertEqual(report, {"one": "created", "two": "created", "three": "created"})


class PointRecordingAtAuthTests(TempTree):
    """One auth.json per system; the recording is pointed at it."""

    def setUp(self) -> None:
        super().setUp()
        self.run_dir = self.make_run()
        self.case_dir = self.make_case("subtasks")
        (self.case_dir / "subtasks.py").write_text(
            "def run(playwright):\n"
            '    context = browser.new_context(storage_state="auth.json")\n',
            encoding="utf-8",
        )

    def test_bare_auth_json_is_rewritten_to_the_system_path(self) -> None:
        result = point_recording_at_auth(self.recordings, "subtasks")

        self.assertEqual(result, "rewritten")
        self.assertIn(
            'storage_state="../auth.json"',
            (self.case_dir / "subtasks.py").read_text(encoding="utf-8"),
        )

    def test_single_quotes_are_handled_too(self) -> None:
        (self.case_dir / "subtasks.py").write_text(
            "context = browser.new_context(storage_state='auth.json')\n", encoding="utf-8"
        )

        point_recording_at_auth(self.recordings, "subtasks")

        self.assertIn(
            "storage_state='../auth.json'",
            (self.case_dir / "subtasks.py").read_text(encoding="utf-8"),
        )

    def test_rewriting_twice_is_a_no_op(self) -> None:
        point_recording_at_auth(self.recordings, "subtasks")

        self.assertEqual(point_recording_at_auth(self.recordings, "subtasks"), "nothing-to-rewrite")

    def test_a_stale_path_is_normalised_too(self) -> None:
        """The path form has changed before; tidy converges whatever it finds."""
        (self.case_dir / "subtasks.py").write_text(
            'context = browser.new_context(storage_state="../../test-cases/auth.json")\n',
            encoding="utf-8",
        )

        self.assertEqual(point_recording_at_auth(self.recordings, "subtasks"), "rewritten")
        self.assertIn(
            'storage_state="../auth.json"',
            (self.case_dir / "subtasks.py").read_text(encoding="utf-8"),
        )

    def test_missing_recording_is_reported(self) -> None:
        self.assertEqual(
            point_recording_at_auth(self.recordings, "absent"), "no-recording"
        )

    def test_the_rewritten_path_actually_resolves(self) -> None:
        """The whole point: the recording must find the one auth file at run time."""
        (self.recordings / "auth.json").write_text("{}", encoding="utf-8")
        point_recording_at_auth(self.recordings, "subtasks")
        link_case(self.run_dir, self.recordings, "subtasks")

        run_dir = os.path.realpath(self.run_dir / "subtasks")
        self.assertTrue(os.path.isfile(os.path.join(run_dir, AUTH_RELATIVE)))


class SystemAuthTests(TempTree):
    """The one real auth.json lives in recordings/; test-cases/ links to it."""

    def setUp(self) -> None:
        super().setUp()
        self.make_run()
        (self.recordings / "auth.json").write_text("{}", encoding="utf-8")

    def test_link_is_created_pointing_at_recordings(self) -> None:
        result = link_system_auth(self.runs, self.recordings)

        self.assertEqual(result, "created")
        link = self.runs / "auth.json"
        self.assertTrue(link.is_symlink())
        self.assertEqual(Path(os.readlink(link)), Path("../recordings/auth.json"))
        self.assertTrue(link.resolve().is_file())

    def test_linking_twice_changes_nothing(self) -> None:
        self.assertEqual(link_system_auth(self.runs, self.recordings), "created")
        self.assertEqual(link_system_auth(self.runs, self.recordings), "already-linked")

    def test_missing_auth_file_is_reported_not_raised(self) -> None:
        (self.recordings / "auth.json").unlink()

        self.assertEqual(link_system_auth(self.runs, self.recordings), "no-auth-file")
        self.assertFalse((self.runs / "auth.json").exists())

    def test_a_real_file_is_never_replaced(self) -> None:
        real = self.runs / "auth.json"
        real.write_text('{"mine": true}', encoding="utf-8")

        self.assertEqual(link_system_auth(self.runs, self.recordings), "skipped")
        self.assertFalse(real.is_symlink())

    def test_a_real_auth_json_stays_flat_in_recordings(self) -> None:
        """Tidy moves loose .py files, never auth.json into a case folder."""
        self.make_case("subtasks")

        tidy_recordings(self.recordings)

        self.assertTrue((self.recordings / "auth.json").is_file())
        self.assertFalse((self.recordings / "auth.json").is_symlink())
        self.assertFalse((self.recordings / "subtasks" / "auth.json").exists())


class CaseStateTests(TempTree):
    def test_case_with_a_recording_is_complete(self) -> None:
        run_dir = self.make_run()
        self.make_case("effort-hours")

        link_case(run_dir, self.recordings, "effort-hours")

        self.assertEqual(case_state(run_dir, "effort-hours"), "complete")

    def test_case_without_a_recording_is_pending(self) -> None:
        run_dir = self.make_run()
        (self.recordings / "sla-versions").mkdir()

        link_case(run_dir, self.recordings, "sla-versions")

        self.assertEqual(case_state(run_dir, "sla-versions"), "pending")

    def test_case_with_nothing_at_all_is_pending(self) -> None:
        run_dir = self.make_run()
        link_case(run_dir, self.recordings, "ghost")

        self.assertEqual(case_state(run_dir, "ghost"), "pending")


class SessionTests(TempTree):
    def test_session_lists_every_case_with_its_state(self) -> None:
        run_dir = self.make_run()
        self.make_case("done-case")
        self.make_case("todo-case", recording=False)
        link_cases(run_dir, self.recordings, ["done-case", "todo-case"])

        text = render_session(
            run_dir,
            run_dir / "Work Platform — Test Manual.md",
            ["done-case", "todo-case"],
            self.recordings,
        )

        self.assertIn("- [x] `done-case` — complete", text)
        self.assertIn("- [ ] `todo-case` — pending", text)

    def test_session_names_the_blocker_when_url_is_missing(self) -> None:
        """Unrecorded and no URL: the human cannot record it yet."""
        run_dir = self.make_run()
        self.make_case("effort-hours", recording=False, url=False)
        link_cases(run_dir, self.recordings, ["effort-hours"])

        text = render_session(run_dir, None, ["effort-hours"], self.recordings)

        self.assertIn("Working on: `effort-hours`", text)
        self.assertIn("url.txt", text)
        self.assertIn("do not infer it", text)

    def test_a_recorded_case_is_not_blocked_on_a_url(self) -> None:
        """The recording already carries its URL in page.goto(). Nothing is blocked."""
        run_dir = self.make_run()
        self.make_case("effort-hours", url=False)
        link_cases(run_dir, self.recordings, ["effort-hours"])

        text = render_session(run_dir, None, ["effort-hours"], self.recordings)

        self.assertNotIn("Blocked", text)
        self.assertIn("The loop is done for this run", text)

    def test_session_does_not_claim_a_blocker_when_url_exists(self) -> None:
        run_dir = self.make_run()
        self.make_case("effort-hours")
        link_cases(run_dir, self.recordings, ["effort-hours"])

        text = render_session(run_dir, None, ["effort-hours"], self.recordings)

        self.assertNotIn("Blocked", text)

    def test_session_reports_done_when_nothing_is_pending(self) -> None:
        run_dir = self.make_run()
        self.make_case("all-done")
        link_cases(run_dir, self.recordings, ["all-done"])

        text = render_session(run_dir, None, ["all-done"], self.recordings)

        self.assertIn("The loop is done for this run", text)

    def test_write_session_replaces_rather_than_appends(self) -> None:
        run_dir = self.make_run()
        self.make_case("one")
        link_cases(run_dir, self.recordings, ["one"])
        write_session(run_dir, None, ["one"], self.recordings)

        self.make_case("two")
        link_cases(run_dir, self.recordings, ["one", "two"])
        write_session(run_dir, None, ["one", "two"], self.recordings)

        text = (run_dir / "session.md").read_text(encoding="utf-8")
        self.assertEqual(text.count("# Run"), 1, "session.md must be rewritten, not appended")


class PrepareTests(TempTree):
    def test_full_pass_tidies_links_and_writes_the_session(self) -> None:
        self.make_run()
        (self.recordings / "effort-hours.py").write_text("# recorded\n", encoding="utf-8")
        (self.recordings / "subtasks").mkdir()
        (self.recordings / "subtasks" / "subtasks.py").write_text("# x\n", encoding="utf-8")

        report = prepare(runs_root=self.runs, recordings_dir=self.recordings)

        self.assertEqual(report["action"], "prepared")
        self.assertEqual(report["run_id"], "002")
        self.assertEqual(report["brief"], "Work Platform — Test Manual.md")
        self.assertEqual([t["case"] for t in report["tidied"]], ["effort-hours"])
        self.assertEqual(report["states"]["subtasks"], "complete")
        self.assertTrue((self.runs / "002" / "subtasks").is_symlink())
        self.assertTrue((self.runs / "002" / "session.md").is_file())

    def test_second_pass_is_a_no_op(self) -> None:
        self.make_run()
        (self.runs / "auth.json").write_text("{}", encoding="utf-8")
        self.make_case("subtasks")

        first = prepare(runs_root=self.runs, recordings_dir=self.recordings)
        second = prepare(runs_root=self.runs, recordings_dir=self.recordings)

        self.assertEqual(first["tidied"], [])
        self.assertEqual(second["tidied"], [])
        self.assertEqual(second["linked"], {"subtasks": "already-linked"})

    def test_dry_run_changes_nothing_on_disk(self) -> None:
        self.make_run()
        (self.recordings / "lazy.py").write_text("# x\n", encoding="utf-8")

        report = prepare(runs_root=self.runs, recordings_dir=self.recordings, dry_run=True)

        self.assertTrue(report["dry_run"])
        self.assertTrue((self.recordings / "lazy.py").is_file(), "must not move anything")
        self.assertFalse((self.recordings / "lazy").exists())
        self.assertFalse((self.runs / "002" / "lazy").exists())
        self.assertFalse((self.runs / "002" / "session.md").exists())

    def test_latest_run_wins_over_older_ones(self) -> None:
        self.make_run("001")
        self.make_run("003")
        self.make_case("subtasks")

        report = prepare(runs_root=self.runs, recordings_dir=self.recordings)

        self.assertEqual(report["run_id"], "003")
        self.assertTrue((self.runs / "003" / "subtasks").is_symlink())
        self.assertFalse((self.runs / "001" / "subtasks").exists())

    def test_explicit_run_id_overrides_latest(self) -> None:
        self.make_run("001")
        self.make_run("002")
        self.make_case("subtasks")

        report = prepare(runs_root=self.runs, recordings_dir=self.recordings, run_id="001")

        self.assertEqual(report["run_id"], "001")
        self.assertTrue((self.runs / "001" / "subtasks").is_symlink())

    def test_explicit_cases_override_discovery(self) -> None:
        self.make_run()
        self.make_case("on-disk")
        self.make_case("named-explicitly")

        report = prepare(
            runs_root=self.runs, recordings_dir=self.recordings, cases=["named-explicitly"]
        )

        self.assertEqual(list(report["states"]), ["named-explicitly"])

    def test_missing_run_id_is_reported_not_raised(self) -> None:
        report = prepare(runs_root=self.runs, recordings_dir=self.recordings, run_id="099")

        self.assertEqual(report["action"], "no-such-run")

    def test_no_run_folder_at_all_is_reported(self) -> None:
        report = prepare(runs_root=self.runs / "elsewhere", recordings_dir=self.recordings)

        self.assertEqual(report["action"], "no-run")

    def test_run_without_a_brief_still_links(self) -> None:
        run_dir = self.runs / "002"
        run_dir.mkdir()
        self.make_case("subtasks")

        report = prepare(runs_root=self.runs, recordings_dir=self.recordings)

        self.assertIsNone(report["brief"])
        self.assertTrue((run_dir / "subtasks").is_symlink())

    def test_case_folders_lists_only_real_directories(self) -> None:
        self.make_case("alpha")
        (self.recordings / "beta.py").write_text("# flat\n", encoding="utf-8")

        self.assertEqual(case_folders(self.recordings), ["alpha"])


if __name__ == "__main__":
    unittest.main()