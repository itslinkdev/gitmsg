"""Rich presentation and single-key terminal input."""

import os
import sys
from collections.abc import Sequence

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .git import StagedFile
from .safety import Redactor


def make_console(no_color: bool = False) -> Console:
    disabled = no_color or "NO_COLOR" in os.environ
    return Console(color_system=None if disabled else "auto")


def show_review(console: Console, files: Sequence[StagedFile], message: str) -> None:
    table = Table(box=box.SIMPLE_HEAD, pad_edge=False)
    table.add_column("Status", style="cyan", no_wrap=True)
    table.add_column("Staged file", overflow="fold")
    table.add_column("+", justify="right", style="green", no_wrap=True)
    table.add_column("-", justify="right", style="red", no_wrap=True)
    for file in files:
        table.add_row(file.status, Text(Redactor()(file.label)), file.added, file.removed)
    console.print(table)
    console.print(Panel(Text(message), title="Proposed commit message", border_style="cyan"))


def read_key() -> str:
    if os.name == "nt":
        import msvcrt

        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            msvcrt.getwch()  # Consume the rest of a Windows function/arrow key.
            return ""
        return key

    import select
    import termios
    import tty

    descriptor = sys.stdin.fileno()
    original = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor)
        key = os.read(descriptor, 1).decode("utf-8", errors="replace")
        if not key:
            raise EOFError
        if key == "\x1b":
            # An arrow's final 'A' must not be mistaken for accept.
            while select.select([descriptor], [], [], 0.02)[0]:
                if not os.read(descriptor, 1):
                    raise EOFError
            return ""
        return key
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, original)


def read_action(console: Console) -> str:
    console.print(Text("[a]ccept [e]dit [r]egenerate [q]uit: "), end="")
    while True:
        key = read_key().lower()
        if key == "\x03":
            raise KeyboardInterrupt
        if key in ("\x04", "\x1a"):
            raise EOFError
        if key in ("a", "e", "r", "q"):
            console.print(key)
            return key
