"""The one command. app/main.py, end to end, without a browser.

Every test drives the real loop over a temp tree. Only step 5 is faked — the
runner is a parameter, so nothing here opens Chromium.
"""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import app.main as main_module
from app.main import (
    EXIT_CANNOT_RUN,
    EXIT_HANDOFF,
    EXIT_OK,
    CannotRun,
    handoff_lines,
    main,
    read_run_cases,
    resolve_run,
    run_case,
    run_cases,
)
from app.tidy import Workspace


class Tree(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.runs = self.root / "test-cases"
        self.recordings = self.root / "recordings"
        self.runs.mkdir()
        self.recordings.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_run(self, run_id: str, cases: list[str] | None = None, brief: bool = True) -> Path:
        run_dir = self.runs / run_id
        run_dir.mkdir()
        if brief:
            (run_dir / "brief.md").write_text("a brief\n", encoding="utf-8")
        if cases is not None:
            (run_dir / "cases.yml").write_text(
                "\n".join(f"- {case}" for case in cases) + "\n", encoding="utf-8"
            )
        return run_dir

    def make_case(self, case: str, recording: bool = True, url: bool = True) -> Path:
        case_dir = self.recordings / case
        case_dir.mkdir(exist_ok=True)
        if recording:
            (case_dir / f"{case}.py").write_text("# recorded\n", encoding="utf-8")
        if url:
            (case_dir / "url.txt").write_text("https://tenant.example/x\n", encoding="utf-8")
        return case_dir

    def call_main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--runs-root", str(self.runs), "--recordings", str(self.recordings), *argv])
        return code, out.getvalue(), err.getvalue()


class ResolveRunTests(Tree):
    def test_the_highest_numbered_run_wins(self) -> None:
        self.make_run("001")
        self.make_run("002")
        self.make_run("010")

        self.assertEqual(resolve_run(self.runs).name, "010")

    def test_nonnumeric_folders_are_not_runs(self) -> None:
        self.make_run("001")
        (self.runs / "notes").mkdir()

        self.assertEqual(resolve_run(self.runs).name, "001")

    def test_no_runs_at_all_is_cannot_run(self) -> None:
        with self.assertRaises(CannotRun):
            resolve_run(self.runs)

    def test_a_named_run_must_exist(self) -> None:
        self.make_run("001")

        with self.assertRaises(CannotRun):
            resolve_run(self.runs, "099")


class CasesYmlTests(Tree):
    def test_a_missing_cases_yml_is_fatal_and_names_the_file(self) -> None:
        run_dir = self.make_run("002", cases=None)

        with self.assertRaises(CannotRun) as caught:
            read_run_cases(run_dir)

        self.assertIn("cases.yml", str(caught.exception))

    def test_a_malformed_cases_yml_is_also_fatal(self) -> None:
        run_dir = self.make_run("002", cases=None)
        (run_dir / "cases.yml").write_text("just a string\n", encoding="utf-8")

        with self.assertRaises(CannotRun):
            read_run_cases(run_dir)

    def test_the_message_never_points_at_a_command_that_cannot_help(self) -> None:
        """app.tidy seeds cases.yml from disk. It cannot read a brief."""
        run_dir = self.make_run("002", cases=None)

        with self.assertRaises(CannotRun) as caught:
            read_run_cases(run_dir)
        message = str(caught.exception)

        self.assertNotIn("app.tidy", message)
        self.assertNotIn("playwright", message)
        self.assertIn("brief", message)

    def test_an_empty_list_is_fatal(self) -> None:
        run_dir = self.make_run("002", cases=[])

        with self.assertRaises(CannotRun):
            read_run_cases(run_dir)

    def test_the_humans_list_is_read_as_written(self) -> None:
        run_dir = self.make_run("002", cases=["effort-hours", "subtasks"])

        self.assertEqual(read_run_cases(run_dir), ["effort-hours", "subtasks"])


class HandoffTests(Tree):
    def test_a_missing_url_is_asked_for_with_a_runnable_path(self) -> None:
        run_dir = self.make_run("002", cases=["effort-hours"])
        self.make_case("effort-hours", url=False)
        Workspace(self.runs, self.recordings).sync_run("002")

        lines = handoff_lines(
            {"missing_py": [], "ask_url_for": ["effort-hours"]},
            run_dir,
            self.recordings,
        )
        text = "\n".join(lines)

        self.assertIn("url.txt", text)
        self.assertIn(str(self.recordings / "effort-hours" / "url.txt"), text)
        self.assertNotIn("<case>", text, "no placeholders reach the human")

    def test_a_missing_recording_comes_with_the_codegen_command(self) -> None:
        run_dir = self.make_run("002", cases=["effort-hours"])
        case_dir = self.make_case("effort-hours", recording=False)  # url present, no .py
        Workspace(self.runs, self.recordings).sync_run("002")

        text = "\n".join(handoff_lines(
            {"missing_py": ["effort-hours"], "ask_url_for": []}, run_dir, self.recordings
        ))

        self.assertIn("playwright codegen", text)
        self.assertIn(str(case_dir / "effort-hours.py"), text)
        self.assertIn("app.main", text)

    def test_a_case_with_neither_is_asked_for_the_url_first(self) -> None:
        run_dir = self.make_run("002", cases=["effort-hours"])
        (self.recordings / "effort-hours").mkdir()
        Workspace(self.runs, self.recordings).sync_run("002")

        text = "\n".join(handoff_lines(
            {"missing_py": ["effort-hours"], "ask_url_for": []}, run_dir, self.recordings
        ))

        self.assertNotIn("playwright codegen", text, "no codegen without a url.txt")


class RunCasesTests(Tree):
    def test_every_case_runs_in_order(self) -> None:
        run_dir = self.make_run("002", cases=["one", "two", "three"])
        for case in ("one", "two", "three"):
            self.make_case(case)
        seen: list[str] = []

        def fake_runner(case: str, _run_dir: Path) -> dict:
            seen.append(case)
            return {"case": case, "status": "passed"}

        summary = run_cases(["one", "two", "three"], run_dir, runner=fake_runner, delay=0)

        self.assertEqual(seen, ["one", "two", "three"])
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["failed"], [])

    def test_one_failure_does_not_stop_the_others(self) -> None:
        run_dir = self.make_run("002", cases=["ok", "broken", "also-ok"])

        def fake_runner(case: str, _run_dir: Path) -> dict:
            return {"case": case, "status": "failed" if case == "broken" else "passed"}

        summary = run_cases(["ok", "broken", "also-ok"], run_dir, runner=fake_runner, delay=0)

        self.assertEqual(len(summary["passed"]), 2)
        self.assertEqual([r["case"] for r in summary["failed"]], ["broken"])

    def test_a_case_with_no_recording_is_reported_not_crashed(self) -> None:
        run_dir = self.make_run("002", cases=["ghost"])
        (run_dir / "ghost").symlink_to(Path("../../recordings/ghost"), target_is_directory=True)
        (self.recordings / "ghost").mkdir()

        summary = run_cases(["ghost"], run_dir, delay=0)

        self.assertEqual(summary["results"][0]["status"], "missing")

    def test_step_delay_holds_between_cases(self) -> None:
        """A human has to see one browser before the next one appears."""
        run_dir = self.make_run("002", cases=["one", "two"])
        slept: list[float] = []

        def fake_runner(case: str, _run_dir: Path) -> dict:
            return {"case": case, "status": "passed"}

        def fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        with mock.patch.object(main_module.time, "sleep", fake_sleep):
            run_cases(["one", "two"], run_dir, runner=fake_runner, delay=2.5)

        self.assertEqual(slept, [2.5], "one pause, between the cases, not before the first")


class SessionStaysAWorkListTests(Tree):
    """session.md says what to do next. It never holds a verdict."""

    def test_a_playback_result_is_not_written_into_it(self) -> None:
        from app.tidy import render_session

        run_dir = self.make_run("002", cases=["one", "two"])
        for case in ("one", "two"):
            self.make_case(case)
        Workspace(self.runs, self.recordings).sync_run("002")

        text = render_session(run_dir, None, ["one", "two"], self.recordings)

        self.assertNotIn("passed", text)
        self.assertNotIn("failed", text)
        self.assertNotIn("Played back", text)
        self.assertIn("Every case has a recording.", text)

    def test_it_names_the_one_thing_to_do_next(self) -> None:
        from app.tidy import render_session

        run_dir = self.make_run("002", cases=["one", "two"])
        self.make_case("one")
        self.make_case("two", recording=False)
        Workspace(self.runs, self.recordings).sync_run("002")

        text = render_session(run_dir, None, ["one", "two"], self.recordings)

        self.assertIn("Working on: `two`", text)


class MainTests(Tree):
    def test_no_run_folder_exits_without_trying(self) -> None:
        code, out, err = self.call_main()

        self.assertEqual(code, EXIT_CANNOT_RUN)
        self.assertIn("cannot run", err)

    def test_missing_cases_yml_exits_immediately(self) -> None:
        self.make_run("002", cases=None)

        code, out, err = self.call_main()

        self.assertEqual(code, EXIT_CANNOT_RUN)
        self.assertIn("cases.yml", err)
        self.assertEqual(out.strip(), "", "nothing was attempted")

    def test_a_missing_recording_stops_before_any_case_runs(self) -> None:
        self.make_run("002", cases=["effort-hours"])
        self.make_case("effort-hours", recording=False)
        (self.recordings / "auth.json").write_text("{}", encoding="utf-8")

        code, out, _ = self.call_main()

        self.assertEqual(code, EXIT_HANDOFF)
        self.assertIn("effort-hours", out)
        self.assertIn("app.main", out)

    def test_every_case_ready_exits_clean(self) -> None:
        self.make_run("002", cases=["effort-hours", "subtasks"])
        for case in ("effort-hours", "subtasks"):
            self.make_case(case)
        (self.recordings / "auth.json").write_text("{}", encoding="utf-8")

        code, out, _ = self.call_main()

        self.assertEqual(code, EXIT_OK, out)
        session = (self.runs / "002" / "session.md").read_text()
        self.assertIn("Every case has a recording.", session)
        self.assertNotIn("passed", session, "session.md never holds a verdict")

    def test_tidy_links_before_the_case_runs(self) -> None:
        run_dir = self.make_run("002", cases=["lazy"])
        (self.recordings / "lazy.py").write_text("# recorded\n", encoding="utf-8")
        (self.recordings / "auth.json").write_text("{}", encoding="utf-8")

        code, out, _ = self.call_main()

        self.assertEqual(code, EXIT_HANDOFF, "no url.txt, so a handoff not a run")
        self.assertTrue((run_dir / "lazy").is_symlink(), "the flat recording was still linked")


if __name__ == "__main__":
    unittest.main()