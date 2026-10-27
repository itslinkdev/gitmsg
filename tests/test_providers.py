import io
import json
import os
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from support import RepoTestCase
from gitmsg.cli import main
from gitmsg.config import Config, ConfigError, load_config
from gitmsg.git import GitError, staged_files
from gitmsg.providers import AnthropicGenerator, NoRedirect, make_generator
from gitmsg.heuristic import HeuristicGenerator
from gitmsg.safety import Redactor


class ProviderTests(RepoTestCase):
    def generator(self, limit=16384, ignore=()):
        return AnthropicGenerator(Config(provider="anthropic", model="claude-test", timeout=2, ignore=list(ignore)), limit)

    def response(self, content=None):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(content or {
            "stop_reason": "end_turn", "content": [{"type": "text", "text": "feat: add greeting"}],
        }).encode()
        return response

    def test_config_defaults_and_validation_without_leaking_values(self):
        self.assertIsInstance(make_generator(load_config(), 100), HeuristicGenerator)
        self.write(".gitmsg.toml", '[gitmsg]\nprovider="anthropic"\nmodel="claude-test"\ntimeout=2\nignore=["private/*"]', stage=False)
        self.assertEqual(load_config(), Config("anthropic", "claude-test", 2, ["private/*"]))
        for contents in ('[gitmsg]\nprovider="unknown-secret"', '[gitmsg]\nprovider="anthropic"',
                         '[gitmsg]\ntimeout=0', '[gitmsg]\ntimeout=true', '[gitmsg]\nignore="secret"',
                         '[gitmsg]\nkey="secret"', '[gitmsg]\nmodel=1', '[gitmsg]\ntimeout=nan',
                         '[gitmsg]\nprovider=[]', '[gitmsg]\nmodel="secret\\nvalue"', 'key="unclosed-secret'):
            with self.subTest(contents=contents):
                self.write(".gitmsg.toml", contents, stage=False)
                with self.assertRaises(ConfigError) as caught:
                    load_config()
                self.assertNotIn("secret", str(caught.exception))

    def test_payload_filters_git_ignores_config_patterns_and_sensitive_paths(self):
        self.write(".gitignore", "ignored/\n")
        for path in ("ignored/api.py", "private/api.py", ".env", "nested/.env.example",
                     "settings.env", "keys/server.pem", "id_ed25519", "dist/api.py", "package-lock.json"):
            self.write(path, "EXCLUDED_CONTENT\n")
        self.write(".gitmsg.toml", "# EXCLUDED_CONTENT\n")
        self.write("src/api.py", "def hello():\n    return 'public'\n")
        (self.directory / "src/api.py").write_text("UNSTAGED_CONTENT", encoding="utf-8")
        generator = self.generator(ignore=["private/*"])
        payload = generator.payload(staged_files())
        self.assertIn(b"public", payload)
        self.assertNotIn(b"EXCLUDED_CONTENT", payload)
        self.assertNotIn(b"UNSTAGED_CONTENT", payload)
        for path in (b"ignored/api.py", b"private/api.py", b".env", b"server.pem", b"package-lock.json"):
            self.assertNotIn(path, payload)
        (self.directory / "src").mkdir(exist_ok=True)
        os.chdir(self.directory / "src")
        self.assertEqual(generator.payload(staged_files()), payload)

    def test_git_global_ignore_and_ignored_rename_source_are_excluded(self):
        self.write("secret.py", "RENAME_SECRET\n")
        self.git("commit", "-qm", "Add fixture")
        self.git("mv", "secret.py", "public.py")
        ignore = self.write("global-ignore", "secret.py\n", stage=False)
        self.git("config", "core.excludesFile", str(ignore))
        self.assertNotIn(b"RENAME_SECRET", self.generator().payload(staged_files()))
        self.assertNotIn(b"public.py", self.generator().payload(staged_files()))

    def test_redacts_before_hunk_and_global_truncation(self):
        secret = "arbitrary-short-value"
        self.write("src/api.py", "password = '" + secret + "'\n" +
                   "key = '''-----BEGIN RSA PRIVATE KEY-----\nshort-private-material\n-----END RSA PRIVATE KEY-----'''\n" +
                   "value = 'ghp_fakecredential'\nvalue = 'sk-fakecredential'\n" +
                   "value = '" + "Z" * 60 + "'\n" + "normal = 1\n")
        for limit in (1, 32, 80, 160, 4096):
            digest = json.loads(self.generator(limit).payload(staged_files()))["messages"][0]["content"]
            self.assertLessEqual(len(digest.encode()), limit)
            for value in (secret, "short-private-material", "fakecredential", "Z" * 20, "BEGIN RSA"):
                self.assertNotIn(value, digest)

    def test_long_lines_and_key_in_path_are_redacted(self):
        self.write("src/key-fixture.py", "prefix = '" + "a" * 4090 + "password=short-secret'\nnext_value=2\n")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "key-fixture"}):
            payload = self.generator().payload(staged_files())
        self.assertNotIn(b"key-fixture", payload)
        self.assertNotIn(b"short-secret", payload)
        self.assertIn(b"next_value", payload)
        self.assertEqual(Redactor()("Authorization: Bearer short\nurl=https://user:pass@host\n"),
                         "[REDACTED]\nurl=[REDACTED]host\n")

    def test_private_keys_in_both_sides_of_a_patch_stay_redacted(self):
        text = (" -----BEGIN PRIVATE KEY-----\n-old-material\n------END PRIVATE KEY-----\n"
                "+new-material\n+-----END PRIVATE KEY-----\n+visible=1\n")
        redacted = Redactor()(text)
        self.assertNotIn("old-material", redacted)
        self.assertNotIn("new-material", redacted)
        self.assertIn("visible=1", redacted)

    def test_show_payload_is_the_exact_request_body_and_never_sends(self):
        self.write("src/api.py", "print('hello')\n")
        self.write(".gitmsg.toml", '[gitmsg]\nprovider="anthropic"\nmodel="claude-test"\ntimeout=2', stage=False)
        output = io.StringIO()
        with patch("sys.stdout", output), patch("gitmsg.providers.request.build_opener") as opener:
            self.assertEqual(main(["--show-payload"]), 0)
            opener.assert_not_called()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "never-print-key"}), \
             patch("gitmsg.providers.request.build_opener") as opener:
            opener.return_value.open.return_value = self.response()
            self.assertEqual(self.generator().generate(staged_files()), "feat: add greeting")
        req = opener.return_value.open.call_args.args[0]
        self.assertEqual(req.data, output.getvalue().encode())
        self.assertEqual(req.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(req.get_header("X-api-key"), "never-print-key")
        self.assertNotIn(b"never-print-key", req.data)
        self.assertEqual(opener.return_value.open.call_args.kwargs, {"timeout": 2})

    def test_one_retry_then_success_uses_identical_bytes(self):
        self.write("api.py", "value=1\n")
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake"}), \
             patch("gitmsg.providers.request.build_opener") as opener:
            opener.return_value.open.side_effect = [URLError("fake"), self.response()]
            self.assertEqual(self.generator().generate(staged_files()), "feat: add greeting")
        calls = opener.return_value.open.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[0].data, calls[1].args[0].data)

    def test_failures_retry_once_then_notice_without_error_details(self):
        self.write("api.py", "value=1\n")
        for failure in (TimeoutError("never-print-key"), URLError("never-print-key"),
                        HTTPError("https://example.invalid", 429, "never-print-key", {}, None)):
            with self.subTest(failure=type(failure).__name__), \
                 patch.dict(os.environ, {"ANTHROPIC_API_KEY": "never-print-key"}), \
                 patch("gitmsg.providers.request.build_opener") as opener, patch("sys.stderr", new_callable=io.StringIO) as err:
                opener.return_value.open.side_effect = failure
                self.assertEqual(self.generator().generate(staged_files()), HeuristicGenerator().generate(staged_files()))
                self.assertEqual(opener.return_value.open.call_count, 2)
                self.assertIn("using offline heuristic", err.getvalue())
                self.assertNotIn("never-print-key", err.getvalue())

    def test_malformed_empty_truncated_and_oversized_responses_fall_back(self):
        self.write("api.py", "value=1\n")
        for raw in (b"not-json", b"[]", b'{"content":[]}',
                    b'{"stop_reason":"max_tokens","content":[]}',
                    json.dumps({"stop_reason": "end_turn", "content": [{"type": "text", "text": "x" * 73}]}).encode(),
                    b"x" * 65_537):
            with self.subTest(raw=raw[:60]), patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake"}), \
                 patch("gitmsg.providers.request.build_opener") as opener, patch("sys.stderr", new_callable=io.StringIO):
                response = self.response()
                response.read.return_value = raw
                opener.return_value.open.return_value = response
                self.assertTrue(self.generator().generate(staged_files()).startswith("feat:"))
                self.assertEqual(opener.return_value.open.call_count, 2)

    def test_missing_key_empty_digest_and_offline_preview_never_send(self):
        self.write("api.py", "value=1\n")
        with patch("gitmsg.providers.request.build_opener") as opener, patch("sys.stderr", new_callable=io.StringIO) as err:
            self.generator().generate(staged_files())
            self.assertIn("missing", err.getvalue())
            self.generator(ignore=["*"]).generate(staged_files())
            self.assertIn("no eligible", err.getvalue())
            self.assertEqual(main(["--show-payload"]), 0)
            self.assertIn("no payload", err.getvalue())
            opener.assert_not_called()

    def test_ignore_failure_and_redirect_fail_closed(self):
        self.write("api.py", "value=1\n")
        files = staged_files()
        with patch("gitmsg.safety.git", return_value=str(self.directory)), \
             patch("gitmsg.safety.subprocess.run", return_value=Mock(returncode=128)):
            with self.assertRaises(GitError):
                self.generator().payload(files)
        self.assertIsNone(NoRedirect().redirect_request(None, None, 307, "redirect", {}, "http://other.invalid"))
