"""Read staged changes and run the commit-message review flow."""

import argparse
import sys
from collections.abc import Sequence

from . import ui
from .config import ConfigError, load_config
from .git import GitError, staged_files
from .heuristic import DEFAULT_MAX_DIGEST_BYTES
from .integration import commit_message, install_hook
from .providers import AnthropicGenerator, Generator, make_generator
from .safety import Redactor


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
    parser.add_argument("command", nargs="?", choices=("generate", "commit", "install-hook"), default="generate")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI styling.")
    parser.add_argument("--show-payload", action="store_true", help="Print the exact JSON request body without sending it.")
    parser.add_argument("--dry-run", action="store_true", help="Preview without committing or installing a hook.")
    parser.add_argument("--yes", action="store_true", help="Accept the proposed commit message without review.")
    parser.add_argument(
        "--max-digest-bytes", type=positive_bytes, default=DEFAULT_MAX_DIGEST_BYTES,
        help=f"Maximum staged digest size in UTF-8 bytes (default: {DEFAULT_MAX_DIGEST_BYTES}).",
    )
    args = parser.parse_args(argv)
    if args.yes and args.command != "commit":
        parser.error("--yes requires commit")
    if args.show_payload and args.command == "install-hook":
        parser.error("--show-payload cannot be used with install-hook")

    try:
        if args.command == "install-hook":
            path = install_hook(args.dry_run)
            print(f"{'Would install' if args.dry_run else 'Installed'} {path}")
            return 0
        interactive = sys.stdout.isatty() and sys.stdin.isatty()
        if args.command == "commit" and not interactive and not (args.yes or args.dry_run or args.show_payload):
            raise GitError("Non-interactive commit requires --yes to accept the message, or --dry-run to preview it.")
        files = staged_files()
        generator = generator if generator is not None else make_generator(load_config(), args.max_digest_bytes)
        if args.show_payload:
            if isinstance(generator, AnthropicGenerator):
                # Write bytes when possible so redirected output stays UTF-8 on Windows.
                payload = generator.payload(files)
                if hasattr(sys.stdout, "buffer"):
                    sys.stdout.buffer.write(payload)
                else:
                    sys.stdout.write(payload.decode("utf-8"))
            else:
                print("gitmsg: heuristic provider is offline; no payload.", file=sys.stderr)
            return 0
        message = Redactor()(generator.generate(files)).strip()
        if args.command == "commit" and args.yes and not args.dry_run:
            print(commit_message(message), end="")
            return 0
        if not interactive:
            print(message)
            return 0

        console = ui.make_console(args.no_color)
        while True:
            ui.show_review(console, files, message)
            action = ui.read_action(console)
            if action == "a":
                if args.command == "commit" and not args.dry_run:
                    console.print(commit_message(message), markup=False, highlight=False, end="")
                else:
                    console.print(message, markup=False, highlight=False)
                return 0
            if action == "e":
                message = Redactor()(console.input("New message (Enter keeps current): ").strip() or message).strip()
            elif action == "r":
                message = Redactor()(generator.generate(files)).strip()
            elif action == "q":
                return 0
    except (GitError, ConfigError) as error:
        print(f"gitmsg: {Redactor()(str(error)).strip()}", file=sys.stderr)
        return 1
    except OSError:
        print("gitmsg: could not read or write a local file.", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
