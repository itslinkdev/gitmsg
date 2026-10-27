import io
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock, patch

from support import RepoTestCase
from gitmsg import cli, hook
from gitmsg.git import GitError, git
from gitmsg.integration import commit_message, install_hook


class IntegrationTests(RepoTestCase):
    def stage(self):
        self.write("src/hello.py", "print('hello')\n")

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "gitmsg.cli", *args],
                              capture_output=True, encoding="utf-8", timeout=15)

    def test_commit_dry_run_preserves_index_and_head(self):
        self.stage()
        before = self.git("diff", "--cached")
        result = self.run_cli("commit", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("feat(src): add"))
        self.assertEqual(self.git("diff", "--cached"), before)
        self.assertEqual(self.git("rev-list", "--all"), "")

    def test_noninteractive_commit_requires_explicit_acceptance_before_generating(self):
        self.stage()
        generator = Mock()
        with patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(cli.main(["commit"], generator), 1)
            self.assertIn("requires --yes", err.getvalue())
        generator.generate.assert_not_called()
        self.assertEqual(self.git("rev-list", "--all"), "")

    def test_commit_yes_and_exact_multiline_message_file_is_removed(self):
        self.stage()
        message = "feat: add greeting\n\n- Support caffè\n- Preserve details"
        with patch("gitmsg.integration.git", wraps=git) as command:
            commit_message(message)
        args = command.call_args.args
        self.assertEqual(args[:2], ("commit", "-F"))
        self.assertFalse(Path(args[2]).exists())
        self.assertEqual(self.git("log", "-1", "--format=%B").strip(), message)
        self.write("README.md", "# docs\n")
        result = self.run_cli("commit", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("diff", "--cached"), "")

    def test_interactive_edit_is_the_committed_message(self):
        self.stage()
        console = Mock()
        console.input.return_value = "fix: use accepted edit"
        with patch("sys.stdout.isatty", return_value=True), patch("sys.stdin.isatty", return_value=True), \
             patch("gitmsg.ui.make_console", return_value=console), patch("gitmsg.ui.show_review"), \
             patch("gitmsg.ui.read_action", side_effect=["e", "a"]):
            self.assertEqual(cli.main(["commit"], Mock(generate=Mock(return_value="feat: initial"))), 0)
        self.assertEqual(self.git("log", "-1", "--format=%B").strip(), "fix: use accepted edit")

    def test_quit_and_interrupt_never_commit(self):
        self.stage()
        for action in ("q", KeyboardInterrupt()):
            with self.subTest(action=type(action).__name__), patch("sys.stdout.isatty", return_value=True), \
                 patch("sys.stdin.isatty", return_value=True), patch("gitmsg.ui.make_console"), \
                 patch("gitmsg.ui.show_review"), patch("gitmsg.ui.read_action", side_effect=[action]):
                self.assertEqual(cli.main(["commit"]), 0 if action == "q" else 130)
            self.assertEqual(self.git("rev-list", "--all"), "")

    def test_failed_commit_reports_error_preserves_index_and_cleans_message(self):
        self.stage()
        reject = self.write(".git/hooks/pre-commit", "#!/bin/sh\nexit 1\n", stage=False)
        reject.chmod(0o755)
        before = self.git("diff", "--cached")
        with patch("gitmsg.integration.git", wraps=git) as command:
            with self.assertRaises(GitError):
                commit_message("feat: add greeting")
        self.assertFalse(Path(command.call_args.args[2]).exists())
        self.assertEqual(self.git("rev-list", "--all"), "")
        self.assertEqual(self.git("diff", "--cached"), before)
        for message in ("", " \n", "feat: bad\0message"):
            with self.subTest(message=repr(message)), self.assertRaises(GitError):
                commit_message(message)

    def test_install_hook_dry_run_without_staged_files_and_refuses_existing(self):
        path = install_hook(dry_run=True)
        self.assertFalse(path.exists())
        result = self.run_cli("install-hook", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Would install", result.stdout)
        self.assertFalse(path.exists())
        result = self.run_cli("install-hook")
        self.assertEqual(result.returncode, 0, result.stderr)
        original = path.read_bytes()
        self.assertNotIn(b"\r", original)
        for dry_run in (False, True):
            with self.assertRaisesRegex(GitError, "refusing to overwrite"):
                install_hook(dry_run)
            self.assertEqual(path.read_bytes(), original)

    def test_existing_empty_hook_or_directory_is_never_overwritten(self):
        path = install_hook(dry_run=True)
        path.touch()
        with self.assertRaises(GitError):
            install_hook()
        self.assertEqual(path.read_bytes(), b"")
        path.unlink()
        path.mkdir()
        with self.assertRaises(GitError):
            install_hook()
        self.assertTrue(path.is_dir())

    def test_custom_hooks_path_from_subdirectory(self):
        self.git("config", "core.hooksPath", "custom hooks")
        nested = self.directory / "nested"
        nested.mkdir()
        os.chdir(nested)
        path = install_hook()
        self.assertEqual(path, self.directory / "custom hooks/prepare-commit-msg")
        self.assertTrue(path.is_file())

    def test_linked_worktree_installs_in_resolved_git_hooks_directory(self):
        self.stage()
        self.git("commit", "-qm", "Add fixture")
        self.git("worktree", "add", "--detach", "linked", "HEAD")
        os.chdir(self.directory / "linked")
        path = install_hook()
        self.assertEqual(path, self.directory / ".git/hooks/prepare-commit-msg")

    def test_real_installed_hook_generates_and_keeps_manual_messages(self):
        self.stage()
        install_hook()
        with patch.dict(os.environ, {"GIT_EDITOR": ":"}):
            self.git("commit", "-q")
        self.assertTrue(self.git("log", "-1", "--format=%B").startswith("feat(src): add src/hello.py"))
        self.write("README.md", "# docs\n")
        self.git("commit", "-qm", "docs: keep manual message")
        self.assertEqual(self.git("log", "-1", "--format=%B").strip(), "docs: keep manual message")
        self.git("commit", "--amend", "--no-edit", "-q")
        self.assertEqual(self.git("log", "-1", "--format=%B").strip(), "docs: keep manual message")
        self.write("README.md", "# more docs\n")
        result = self.run_cli("commit", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_hook_preserves_sources_existing_text_and_comments(self):
        self.stage()
        path = self.write("message.txt", "", stage=False)
        for source in ("message", "commit", "merge", "squash", "template"):
            with self.subTest(source=source), patch("gitmsg.hook.make_generator") as generator:
                self.assertEqual(hook.main([str(path), source]), 0)
                self.assertEqual(path.read_text(), "")
                generator.assert_not_called()
        path.write_text("my existing message\n", encoding="utf-8")
        self.assertEqual(hook.main([str(path)]), 0)
        self.assertEqual(path.read_text(), "my existing message\n")
        self.git("config", "core.commentChar", ";")
        path.write_text("\n; Preserve Git status comments\n", encoding="utf-8")
        self.assertEqual(hook.main([str(path)]), 0)
        self.assertTrue(path.read_text().startswith("feat(src): add"))
        self.assertIn("; Preserve Git status comments", path.read_text())

    def test_hook_without_staged_files_or_bad_config_leaves_message_alone(self):
        path = self.write("message.txt", "", stage=False)
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertEqual(hook.main([str(path)]), 0)
            self.assertIn("leaving message unchanged", err.getvalue())
        self.stage()
        self.write(".gitmsg.toml", '[gitmsg]\nprovider="bad"', stage=False)
        with patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(hook.main([str(path)]), 0)
        self.assertEqual(path.read_text(), "")

    def test_payload_on_commit_does_not_commit_or_require_acceptance(self):
        self.stage()
        self.write(".gitmsg.toml", '[gitmsg]\nprovider="anthropic"\nmodel="claude-test"', stage=False)
        result = self.run_cli("commit", "--show-payload")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"model":"claude-test"', result.stdout)
        self.assertEqual(self.git("rev-list", "--all"), "")
