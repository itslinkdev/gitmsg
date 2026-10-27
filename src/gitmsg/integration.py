"""Commit accepted text and install a non-destructive Git hook."""

import os
from pathlib import Path
import shlex
import sys
import tempfile

from .git import GitError, git


def commit_message(message: str) -> str:
    if not message.strip() or "\0" in message:
        raise GitError("Cannot commit an empty message or a message containing NUL.")
    # Close the file before Git opens it, including on Windows.
    with tempfile.TemporaryDirectory(prefix="gitmsg-") as directory:
        path = Path(directory) / "message.txt"
        path.write_text(message.rstrip() + "\n", encoding="utf-8", newline="\n")
        return git("commit", "-F", str(path))


def install_hook(dry_run: bool = False) -> Path:
    root = git("rev-parse", "--show-toplevel").strip()
    path = Path(git("-C", root, "rev-parse", "--path-format=absolute", "--git-path", "hooks/prepare-commit-msg").strip())
    if os.path.lexists(path):
        raise GitError("prepare-commit-msg already exists; refusing to overwrite it.")
    if dry_run:
        return path
    python = shlex.quote(Path(sys.executable).as_posix())
    script = f'#!/bin/sh\nexec {python} -m gitmsg.hook "$@"\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        hook = path.open("x", encoding="utf-8", newline="\n")
    except FileExistsError:
        raise GitError("prepare-commit-msg already exists; refusing to overwrite it.") from None
    try:
        with hook:
            hook.write(script)
        path.chmod(0o755)
    except OSError:
        path.unlink(missing_ok=True)
        raise
    return path
