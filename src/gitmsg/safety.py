"""Conservative outbound path filtering and secret redaction."""

from collections.abc import Sequence
from fnmatch import fnmatchcase
import os
from pathlib import PurePosixPath
import re
import subprocess

from .git import GitError, StagedFile, git


ASSIGNMENT = re.compile(
    r"(?i)(?:[\w.-]*(?:secret|token|password|passwd|credential|api[_-]?key|private[_-]?key|access[_-]?key)[\w.-]*"
    r"[\"']?\s*[:=]|(?:authorization|cookie)\s*[:=])"
)
TOKEN = re.compile(
    r"(?:sk-[\w-]+|gh[pousr]_[\w]+|github_pat_[\w]+|(?:AKIA|ASIA)[A-Z0-9]+"
    r"|AIza[\w-]+|xox[baprs]-[\w-]+|eyJ[\w.-]+|(?i:bearer)\s+\S+"
    r"|[A-Za-z0-9_+/=-]{32,}|https?://[^\s/@:]+:[^\s/@]+@)"
)


class Redactor:
    def __init__(self):
        self.private_key = False

    def __call__(self, text: str) -> str:
        lines = []
        for line in text.splitlines(keepends=True):
            key = os.environ.get("ANTHROPIC_API_KEY", "")
            if key:
                line = line.replace(key, "[REDACTED]")
            begin = "-----BEGIN " in line and "PRIVATE KEY-----" in line
            end = "-----END " in line and "PRIVATE KEY-----" in line
            if self.private_key or begin or end or ASSIGNMENT.search(line):
                self.private_key = (self.private_key or begin) and not end
                prefix = line[:1] if line[:1] in ("+", "-", " ") else ""
                lines.append(prefix + "[REDACTED]\n")
            else:
                lines.append(TOKEN.sub("[REDACTED]", line))
        return "".join(lines)


def sensitive_path(path: str) -> bool:
    parts = PurePosixPath(path.lower()).parts
    return any(
        part == ".env" or part.startswith(".env.") or part.endswith(".env")
        or part in {".gitmsg.toml", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
        or part.endswith((".pem", ".key", ".p12", ".pfx"))
        for part in parts
    )


def outbound_files(files: Sequence[StagedFile], ignore: Sequence[str]) -> list[StagedFile]:
    paths = [path for file in files for path in (file.path, file.old_path) if path]
    root = git("rev-parse", "--show-toplevel").strip()
    # --no-index also checks force-added/tracked files against Git's ignore rules.
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-z", "--stdin"],
        input="\0".join(paths) + "\0", capture_output=True, encoding="utf-8", cwd=root,
    )
    if result.returncode not in (0, 1):
        raise GitError("Could not check ignored paths; no payload was sent.")
    ignored = set(result.stdout.split("\0"))

    def excluded(path):
        return (path in ignored or sensitive_path(path)
                or any(fnmatchcase(path, pattern) for pattern in ignore))

    return [file for file in files if not any(excluded(path) for path in (file.path, file.old_path) if path)]
