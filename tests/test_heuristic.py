import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from gitmsg.git import GitError, patch_hunks, staged_files
from gitmsg.heuristic import HeuristicGenerator, build_digest, infer_scope


class HeuristicTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        previous = Path.cwd()
        os.chdir(self.directory)
        self.addCleanup(os.chdir, previous)
        environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        isolated = patch.dict(os.environ, environment, clear=True)
        isolated.start()
        self.addCleanup(isolated.stop)
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")

    def git(self, *args):
        return subprocess.run(
            ["git", *args], check=True, capture_output=True, encoding="utf-8",
        ).stdout

    def write(self, path, content):
        destination = self.directory / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            destination.write_bytes(content)
        else:
            destination.write_text(content, encoding="utf-8")
        self.git("add", "--", path)

    def commit(self):
        self.git("-c", "user.name=Codex", "-c", "user.email=codex@example.invalid",
                 "commit", "-qm", "Add fixture")

    def message(self, kind, scope=None):
        message = HeuristicGenerator().generate(staged_files())
        prefix = f"{kind}({scope}): " if scope else f"{kind}: "
        self.assertTrue(message.startswith(prefix), message)
        self.assertLessEqual(len(message.splitlines()[0]), 72)
        self.assertBetweenBullets(message)
        return message

    def assertBetweenBullets(self, message):
        bullets = [line for line in message.splitlines() if line.startswith("- ")]
        self.assertGreaterEqual(len(bullets), 1)
        self.assertLessEqual(len(bullets), 5)

    def test_docs_only(self):
        self.write("docs/usage.md", "# Usage\nRun the tool.\n")
        self.assertEqual(self.message("docs", "docs"),
                         "docs(docs): update docs/usage.md\n\n- Add docs/usage.md (+2/-0)")

    def test_tests_only(self):
        self.write("tests/test_api.py", "def test_api():\n    assert True\n")
        self.message("test", "tests")

    def test_new_feature_ignores_unstaged_edits(self):
        self.write("src/api.py", "def greet():\n    return 'hello'\n")
        before = self.git("diff", "--cached")
        (self.directory / "src/api.py").write_text("# UNSTAGED_SECRET\n", encoding="utf-8")
        files = staged_files()
        digest = build_digest(files)
        self.assertIn("def greet", digest)
        self.assertNotIn("UNSTAGED_SECRET", digest)
        self.assertIn("feat(src): add src/api.py", self.message("feat", "src"))
        self.assertEqual(self.git("diff", "--cached"), before)

    def test_rename_preserves_both_paths_and_zero_counts(self):
        self.write("src/old.py", "value = 1\n")
        self.commit()
        self.git("mv", "src/old.py", "src/new.py")
        file, = staged_files()
        self.assertEqual((file.status, file.old_path, file.path, file.added, file.removed),
                         ("R", "src/old.py", "src/new.py", "0", "0"))
        self.assertIn("src/old.py -> src/new.py", build_digest([file]))
        self.assertIn("rename src/new.py", self.message("refactor", "src"))

    def test_delete_reads_staged_removed_content(self):
        self.write("src/old.py", "obsolete = True\n")
        self.commit()
        self.git("rm", "src/old.py")
        file, = staged_files()
        self.assertEqual((file.status, file.added, file.removed), ("D", "0", "1"))
        self.assertIn("-obsolete = True", build_digest([file]))
        self.assertIn("- Remove src/old.py (+0/-1)", self.message("refactor", "src"))

    def test_lockfile_only(self):
        self.write("package-lock.json", '{"packages": {"example": "1.0"}}\n')
        files = staged_files()
        self.assertEqual(build_digest(files), "")
        self.message("chore")

    def test_huge_diff_is_byte_bounded_and_prioritizes_source(self):
        self.write("docs/large.md", "unimportant documentation\n" * 10_000)
        self.write("src/feature.py", "def important():\n    return 'é🙂'\n" + "# filler\n" * 10_000)
        files = staged_files()
        for limit in (1, 17, 128, 512, 4096):
            with self.subTest(limit=limit):
                digest = build_digest(files, limit)
                self.assertLessEqual(len(digest.encode("utf-8")), limit)
                self.assertEqual(digest, build_digest(files, limit))
        digest = build_digest(files, 512)
        self.assertIn("src/feature.py", digest)
        self.assertIn("def important", digest)
        self.assertIn("[truncated]", digest)
        self.message("feat")

    def test_binary_file(self):
        self.write("assets/image.bin", b"\x00\xff\x01")
        file, = staged_files()
        self.assertTrue(file.binary)
        self.assertEqual((file.added, file.removed), ("-", "-"))
        self.assertEqual(build_digest([file]), "")
        self.assertIn("(binary)", self.message("chore", "assets"))

    def test_fix_inferred_from_added_guard(self):
        self.write("src/api.py", "def greet(name):\n    return name.upper()\n")
        self.commit()
        self.write("src/api.py", "def greet(name):\n    if name is None:\n        return ''\n    return name.upper()\n")
        self.message("fix", "src")

    def test_modified_file_with_new_function_is_feature(self):
        self.write("src/api.py", "value = 1\n")
        self.commit()
        self.write("src/api.py", "value = 1\n\ndef greet():\n    return 'hello'\n")
        self.message("feat", "src")

    def test_existing_implementation_changes_are_refactor(self):
        self.write("src/api.py", "value = 1 + 1\n")
        self.commit()
        self.write("src/api.py", "value = 2\n")
        self.message("refactor", "src")

    def test_accompanying_tests_do_not_change_source_inference(self):
        self.write("src/api.py", "value = 1 + 1\n")
        self.commit()
        self.write("src/api.py", "value = 2\n")
        self.write("tests/test_api.py", "def test_guard():\n    if value is None:\n        raise ValueError()\n")
        self.message("refactor")

    def test_build_configuration(self):
        self.write("pyproject.toml", '[project]\nname = "example"\n')
        self.message("build")

    def test_ci_configuration(self):
        self.write(".github/workflows/test.yml", "name: Test\non: push\n")
        self.message("ci", ".github")

    def test_skips_lock_minified_generated_and_binary_patches(self):
        for path in ("uv.lock", "web/app.min.js", "dist/app.js", "src/schema.generated.py",
                     "src/message_pb2.py", "src/model.g.cs", "generated/model.py", "src/generated_client.py"):
            self.write(path, "DO_NOT_INCLUDE\n" * 100)
        self.write("assets/data.bin", b"\x00DO_NOT_INCLUDE")
        self.write("src/api.py", "value = 'include me'\n")
        digest = build_digest(staged_files())
        self.assertIn("include me", digest)
        self.assertNotIn("DO_NOT_INCLUDE", digest)
        self.assertNotIn("uv.lock", digest)

    def test_later_important_hunk_wins_over_earlier_bulk(self):
        original = [f"value_{i} = {i}\n" for i in range(1000)]
        self.write("src/api.py", "".join(original))
        self.commit()
        changed = original.copy()
        changed[:200] = [f"value_{i} = {i + 1}\n" for i in range(200)]
        changed[900] = "if result is None:  # prevent a crash\n"
        self.write("src/api.py", "".join(changed))
        digest = build_digest(staged_files(), 256)
        self.assertIn("prevent a crash", digest)
        self.assertNotIn("+value_0", digest)
        self.assertLessEqual(len(digest.encode("utf-8")), 256)
        self.message("fix", "src")

    def test_long_single_line_is_truncated(self):
        self.write("src/data.py", "value = '" + "🙂" * 100_000 + "'\n")
        for limit in (300, 4096):
            with self.subTest(limit=limit):
                digest = build_digest(staged_files(), limit)
                self.assertLessEqual(len(digest.encode("utf-8")), limit)
                self.assertNotIn("�", digest)
                self.assertIn("[truncated]", digest)

    def test_body_limits_and_ranks_significant_files(self):
        self.write("package-lock.json", "lock data\n" * 5000)
        self.write("docs/readme.md", "docs\n" * 1000)
        for number in range(6):
            self.write(f"src/file{number}.py", "value = 1\n" * (number + 1))
        message = self.message("feat")
        bullets = message.split("\n\n")[1].splitlines()
        self.assertEqual(len(bullets), 5)
        self.assertTrue(bullets[0].startswith("- Add src/file5.py"), bullets)
        self.assertNotIn("package-lock", message)

    def test_scope_and_subject_limits(self):
        self.write("src/" + "a" * 150 + ".py", "value = 1\n")
        self.assertEqual(len(self.message("feat", "src").splitlines()[0]), 72)
        self.write("tests/test_api.py", "assert True\n")
        self.assertEqual(infer_scope(staged_files()), "")
        self.message("feat")

    def test_cross_directory_rename_has_no_scope(self):
        self.write("src/api.py", "value = 1\n")
        self.commit()
        (self.directory / "lib").mkdir()
        self.git("mv", "src/api.py", "lib/api.py")
        self.message("refactor")

    def test_long_scope_is_preserved_when_subject_has_room(self):
        scope = "module_" + "a" * 25
        self.write(f"{scope}/api.py", "value = 1\n")
        self.message("feat", scope)

    def test_oversized_scope_keeps_subject_imperative_and_bounded(self):
        self.write("a" * 100 + "/api.py", "value = 1\n")
        self.assertTrue(self.message("feat").startswith("feat: add "))

    def test_modified_rename_and_empty_file(self):
        self.write("src/old.py", "".join(f"value_{i} = {i}\n" for i in range(50)))
        self.commit()
        self.git("mv", "src/old.py", "src/new.py")
        with (self.directory / "src/new.py").open("a", encoding="utf-8") as file:
            file.write("new_value = 100\n")
        self.git("add", "src/new.py")
        self.write("src/empty.py", "")
        files = staged_files()
        renamed = next(file for file in files if file.status == "R")
        self.assertEqual((renamed.old_path, renamed.path, renamed.added, renamed.removed),
                         ("src/old.py", "src/new.py", "1", "0"))
        digest = build_digest(files)
        self.assertIn("+new_value = 100", digest)
        self.assertIn("src/empty.py [A +0/-0]", digest)
        self.message("feat", "src")

    def test_digest_from_subdirectory_and_literal_path(self):
        self.write("src/[api].py", "value = 'literal path'\n")
        self.write("src/api.py", "value = 'other file'\n")
        files = staged_files()
        literal = next(file for file in files if "[api]" in file.path)
        os.chdir(self.directory / "src")
        digest = build_digest([literal])
        self.assertIn("literal path", digest)
        self.assertNotIn("other file", digest)
        self.assertEqual(len(staged_files()), 2)

    def test_invalid_limits_and_empty_generation(self):
        for limit in (0, -1):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                build_digest([], limit)
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                HeuristicGenerator(limit)
        with self.assertRaises(ValueError):
            HeuristicGenerator().generate([])

    def test_missing_git_and_patch_failure_report_git_errors(self):
        self.write("src/api.py", "value = 1\n")
        file, = staged_files()
        with patch("gitmsg.git.subprocess.Popen", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(GitError, "not installed"):
                list(patch_hunks(file, 256))
        os.chdir(self.directory.parent)
        with self.assertRaises(GitError):
            list(patch_hunks(file, 256))


if __name__ == "__main__":
    unittest.main()
