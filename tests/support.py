"""Temporary repositories with isolated Git configuration and no live HTTP."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


class RepoTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        previous = Path.cwd()
        os.chdir(self.directory)
        self.addCleanup(os.chdir, previous)
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith("GIT_") and key != "ANTHROPIC_API_KEY"}
        environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        isolated = patch.dict(os.environ, environment, clear=True)
        isolated.start()
        self.addCleanup(isolated.stop)
        network = patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Live HTTP forbidden in tests"))
        network.start()
        self.addCleanup(network.stop)
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "user.name", "Codex")
        self.git("config", "user.email", "codex@example.invalid")

    def git(self, *args):
        return subprocess.run(["git", *args], check=True, capture_output=True, encoding="utf-8").stdout

    def write(self, path, content, *, stage=True):
        destination = self.directory / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        if stage:
            self.git("add", "-f", "--", path)
        return destination
