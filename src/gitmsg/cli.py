"""Read staged changes and run the commit-message review flow."""

import argparse
import sys
from collections.abc import Sequence

from . import ui
from .config import ConfigError, load_config
from .git import GitError, StagedFile, staged_files
from .heuristic import DEFAULT_MAX_DIGEST_BYTES
from .providers import AnthropicGenerator, Generator, make_generator


def positive_bytes(value: str) -> int:
    try:
        size = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer byte count") from error
    if size <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer byte count")
    return size


def main(argv: Sequence[str] | None = None, generator: Generator | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI styling.")
    parser.add_argument("--show-payload", action="store_true", help="Print the exact JSON request body without sending it.")
    parser.add_argument(
        "--max-digest-bytes", type=positive_bytes, default=DEFAULT_MAX_DIGEST_BYTES,
        help=f"Maximum staged digest size in UTF-8 bytes (default: {DEFAULT_MAX_DIGEST_BYTES}).",
    )
    args = parser.parse_args(argv)

    try:
        files = staged_files()
        generator = generator if generator is not None else make_generator(load_config(), args.max_digest_bytes)
        if args.show_payload:
            if isinstance(generator, AnthropicGenerator):
                sys.stdout.write(generator.payload(files).decode("utf-8"))
            else:
                print("gitmsg: heuristic provider is offline; no payload.", file=sys.stderr)
            return 0
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
    except (GitError, ConfigError) as error:
        print(f"gitmsg: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
