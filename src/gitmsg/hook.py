"""Prepare a suggestion only for an ordinary commit without an existing message."""

from collections.abc import Sequence
from pathlib import Path
import sys

from .config import ConfigError, load_config
from .git import GitError, git, staged_files
from .heuristic import DEFAULT_MAX_DIGEST_BYTES
from .providers import make_generator
from .safety import Redactor


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("gitmsg hook: missing message file.", file=sys.stderr)
        return 1
    # -m/-F, amend, merge, squash and templates belong to Git and the user.
    if len(args) > 1 and args[1]:
        return 0
    try:
        path = Path(args[0])
        original = path.read_text(encoding="utf-8")
        comment = git("config", "--get", "--default", "#", "core.commentChar").strip()
        comment = "#" if comment == "auto" else comment
        if any(line.strip() and not line.startswith(comment) for line in original.splitlines()):
            return 0
        config = load_config()
        message = make_generator(config, DEFAULT_MAX_DIGEST_BYTES).generate(staged_files())
        message = Redactor()(message).strip()
        path.write_text(message + "\n\n" + original, encoding="utf-8", newline="\n")
        return 0
    except (GitError, ConfigError) as error:
        print(f"gitmsg hook: {Redactor()(str(error)).strip()}; leaving message unchanged.", file=sys.stderr)
        return 0
    except (OSError, UnicodeError):
        print("gitmsg hook: could not read or write the message file.", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
