"""Read staged metadata and stream patches without changing the index."""

import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass


DIFF_OPTIONS = ("diff", "--cached", "--find-renames", "--no-ext-diff", "--no-textconv", "--no-relative")


@dataclass
class StagedFile:
    status: str
    path: str
    added: str
    removed: str
    old_path: str | None = None

    @property
    def label(self) -> str:
        return f"{self.old_path} -> {self.path}" if self.old_path else self.path

    @property
    def binary(self) -> bool:
        return self.added == "-" or self.removed == "-"

    @property
    def changes(self) -> int:
        return 0 if self.binary else int(self.added) + int(self.removed)


class GitError(Exception):
    pass


def git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError as error:
        raise GitError("Git is not installed or is not on PATH.") from error
    if result.returncode:
        detail = result.stderr.strip()
        if "not a git repository" in detail.lower():
            raise GitError("Not a Git repository. Run gitmsg inside a working tree.")
        raise GitError(detail or "Git could not read staged changes.")
    return result.stdout


def staged_files() -> list[StagedFile]:
    if git("rev-parse", "--is-inside-work-tree").strip() != "true":
        raise GitError("Not a Git working tree. Run gitmsg inside a working tree.")
    names = git(*DIFF_OPTIONS, "--name-status", "-z")
    if not names:
        raise GitError("Nothing staged. Stage changes with git add first.")

    counts = {}
    # NUL separators preserve tabs, newlines, and rename pairs in filenames.
    stats = iter(git(*DIFF_OPTIONS, "--numstat", "-z").split("\0")[:-1])
    for row in stats:
        added, removed, path = row.split("\t", 2)
        if not path:
            next(stats)
            path = next(stats)
        counts[path] = (added, removed)

    files = []
    entries = iter(names.split("\0")[:-1])
    for status in entries:
        path = next(entries)
        old_path = None
        if status[0] in ("R", "C"):
            old_path, path = path, next(entries)
        if status[0] == "U":
            raise GitError("Resolve merge conflicts before generating a message.")
        added, removed = counts[path]
        files.append(StagedFile(status[0], path, added, removed, old_path))
    return files


def patch_hunks(file: StagedFile, max_bytes: int) -> Iterator[str]:
    paths = [f":(top,literal){path}" for path in (file.path, file.old_path) if path]
    command = ["git", *DIFF_OPTIONS, "--no-color", "--unified=3", "--", *paths]
    # Stream even a huge single line; stderr goes to disk to avoid pipe deadlocks.
    with tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        except FileNotFoundError as error:
            raise GitError("Git is not installed or is not on PATH.") from error
        with process:
            with process.stdout:
                hunk = bytearray()
                truncated = False
                in_hunk = False
                line_start = True
                while chunk := process.stdout.readline(4096):
                    if line_start and chunk.startswith(b"@@ "):
                        if in_hunk:
                            yield hunk.decode("utf-8", errors="ignore") + ("\n[truncated]\n" if truncated else "")
                        hunk.clear()
                        truncated = False
                        in_hunk = True
                    if in_hunk:
                        available = max(0, max_bytes - len(hunk))
                        truncated |= len(chunk) > available
                        hunk.extend(chunk[:available])
                    line_start = chunk.endswith(b"\n")
                if in_hunk:
                    yield hunk.decode("utf-8", errors="ignore") + ("\n[truncated]\n" if truncated else "")
                else:
                    yield ""
            if process.wait():
                errors.seek(0)
                detail = errors.read(4096).decode("utf-8", errors="replace").strip()
                raise GitError(detail or "Git could not read the staged patch.")
