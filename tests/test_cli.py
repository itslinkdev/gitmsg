import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from gitmsg import cli, ui, git as staged_git


class NonInteractiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        self.environment.update(
            PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            FORCE_COLOR="1",
        )

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.directory, env=self.environment,
            capture_output=True, text=True, check=True,
        ).stdout

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "gitmsg.cli", *args],
            cwd=self.directory, env=self.environment,
            capture_output=True, text=True, timeout=10,
        )

    def stage_file(self):
        self.git("init", "-q")
        (self.directory / "example.txt").write_text("one\ntwo\n", encoding="utf-8")
        self.git("add", "example.txt")

    def test_pipe_prints_only_message_and_preserves_index(self):
        self.stage_file()
        before = self.git("diff", "--cached")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "docs: update example.txt\n\n- Add example.txt (+2/-0)\n")
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.git("diff", "--cached"), before)

    def test_no_color_option_and_environment_in_a_pipe(self):
        self.stage_file()
        for arguments, environment in ((["--no-color"], {}), ([], {"NO_COLOR": ""})):
            with self.subTest(arguments=arguments, environment=environment):
                self.environment.update(environment)
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "docs: update example.txt\n\n- Add example.txt (+2/-0)\n")
                self.assertEqual(result.stderr, "")

    def test_outside_repository_reports_error_only_on_stderr(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Not a Git repository", result.stderr)

    def test_unstaged_changes_report_nothing_staged(self):
        self.git("init", "-q")
        (self.directory / "example.txt").write_text("not staged", encoding="utf-8")
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Nothing staged", result.stderr)

    def test_binary_rename_and_tab_in_path(self):
        self.stage_file()
        self.git("-c", "user.name=Codex", "-c", "user.email=codex@example.invalid",
                 "commit", "-qm", "Add fixture")
        self.git("mv", "example.txt", "renamed.txt")
        (self.directory / "binary.bin").write_bytes(b"\x00\x01\xff")
        self.git("add", "binary.bin")
        # Git's -z format permits a tab even on hosts that cannot create such a filename.
        with patch("gitmsg.git.git", side_effect=[
            "true\n", "A\0tab\tname\0", "1\t0\ttab\tname\0"
        ]):
            self.assertEqual(cli.staged_files(), [ui.StagedFile("A", "tab\tname", "1", "0")])
        original_git = staged_git.git
        with patch("gitmsg.git.git", side_effect=lambda *args: original_git("-C", str(self.directory), *args)):
            files = cli.staged_files()
        self.assertIn(ui.StagedFile("R", "renamed.txt", "0", "0", "example.txt"), files)
        self.assertIn(ui.StagedFile("A", "binary.bin", "-", "-"), files)
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("docs: update documentation\n\n"), result.stdout)
        self.assertIn("- Rename example.txt -> renamed.txt (+0/-0)", result.stdout)
        self.assertIn("- Add binary.bin (binary)", result.stdout)

    def test_digest_limit_is_configurable_and_validated(self):
        self.stage_file()
        self.assertEqual(self.run_cli("--max-digest-bytes", "32").returncode, 0)
        for value in ("0", "-1", "not-a-number"):
            with self.subTest(value=value):
                result = self.run_cli("--max-digest-bytes", value)
                self.assertEqual(result.returncode, 2)
                self.assertIn("positive integer", result.stderr)


class ReviewTests(unittest.TestCase):
    def test_review_treats_paths_and_message_as_literal_text(self):
        output = io.StringIO()
        console = ui.Console(file=output, color_system=None, width=90)
        ui.show_review(console, [ui.StagedFile("A", "[red]file.txt", "2", "0")], "fix: [blue] text")
        self.assertIn("[red]file.txt", output.getvalue())
        self.assertIn("fix: [blue] text", output.getvalue())

    def test_color_can_be_disabled_even_with_forced_color(self):
        for arguments, environment in ((True, {}), (False, {"NO_COLOR": ""})):
            with self.subTest(no_color=arguments), patch.dict(os.environ, environment):
                with patch.dict(os.environ, {"FORCE_COLOR": "1"}):
                    self.assertIsNone(ui.make_console(arguments).color_system)

    def test_single_key_actions_ignore_other_keys(self):
        console = ui.Console(file=io.StringIO(), color_system=None)
        with patch("gitmsg.ui.read_key", side_effect=["x", "", "A"]):
            self.assertEqual(ui.read_action(console), "a")

    def test_edit_regenerate_and_accept(self):
        generator = unittest.mock.Mock()
        generator.generate.side_effect = ["first message", "regenerated message"]
        console = unittest.mock.Mock()
        console.input.return_value = "edited message"
        with patch("gitmsg.cli.staged_files", return_value=[]), \
             patch("sys.stdout.isatty", return_value=True), \
             patch("sys.stdin.isatty", return_value=True), \
             patch("gitmsg.ui.make_console", return_value=console), \
             patch("gitmsg.ui.show_review") as show, \
             patch("gitmsg.ui.read_action", side_effect=["e", "r", "a"]):
            self.assertEqual(cli.main([], generator), 0)
        self.assertEqual([call.args[2] for call in show.call_args_list],
                         ["first message", "edited message", "regenerated message"])
        console.print.assert_called_once_with("regenerated message", markup=False, highlight=False)
        self.assertEqual(generator.generate.call_count, 2)

    def test_quit_does_not_print_selected_message(self):
        console = unittest.mock.Mock()
        with patch("gitmsg.cli.staged_files", return_value=[]), \
             patch("sys.stdout.isatty", return_value=True), \
             patch("sys.stdin.isatty", return_value=True), \
             patch("gitmsg.ui.make_console", return_value=console), \
             patch("gitmsg.ui.show_review"), \
             patch("gitmsg.ui.read_action", return_value="q"):
            self.assertEqual(cli.main([], unittest.mock.Mock()), 0)
        console.print.assert_not_called()


if __name__ == "__main__":
    unittest.main()
