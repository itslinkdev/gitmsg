"""Read staged changes and run the commit-message review flow."""

import argparse
import subprocess
import sys
from collections.abc import Sequence
from typing import Protocol

from . import ui
from .ui import StagedFile


class Generator(Protocol):
    def generate(self, files: Sequence[StagedFile]) -> str: ...


class StubGenerator:
    def generate(self, files: Sequence[StagedFile]) -> str:
        return "chore: update staged files"


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

    options = ("diff", "--cached", "--find-renames", "--no-ext-diff", "--no-textconv")
    names = git(*options, "--name-status", "-z")
    if not names:
        raise GitError("Nothing staged. Stage changes with git add first.")

    counts = {}
    # NUL separators keep tabs and newlines in filenames from breaking the rows.
    stats = iter(git(*options, "--numstat", "-z").split("\0")[:-1])
    for row in stats:
        added, removed, path = row.split("\t", 2)
        if not path:
            next(stats)  # A rename lists the old path before the new one.
            path = next(stats)
        counts[path] = (added, removed)

    files = []
    entries = iter(names.split("\0")[:-1])
    for status in entries:
        path = next(entries)
        label = path
        if status[0] in ("R", "C"):
            old_path = path
            path = next(entries)
            label = f"{old_path} -> {path}"
        added, removed = counts[path]
        files.append(StagedFile(status[0], label, added, removed))
    return files


def main(argv: Sequence[str] | None = None, generator: Generator | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI styling.")
    args = parser.parse_args(argv)

    try:
        files = staged_files()
        generator = generator if generator is not None else StubGenerator()
        message = generator.generate(files)
        if not sys.stdout.isatty() or not sys.stdin.isatty():
            print(message)
            return 0

        console = ui.make_console(args.no_color)
        while True:
            ui.show_review(console, files, message)
            action = ui.read_action(console)
            if action == "a":
                console.print(message, markup=False, highlight=False)
                return 0
            if action == "e":
                message = console.input("New message (Enter keeps current): ").strip() or message
            elif action == "r":
                message = generator.generate(files)
            elif action == "q":
                return 0
    except GitError as error:
        print(f"gitmsg: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
