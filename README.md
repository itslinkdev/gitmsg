# gitmsg

A small Python 3.11+ CLI that proposes a message for staged Git changes.
Git must be on PATH. The only runtime dependency is `rich`.

## Install and run

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\gitmsg
```

Run `gitmsg` inside the repository whose staged changes you want to review.
Stage files with `git add` first.

An interactive terminal shows a compact table with status letters, paths and
added/removed line counts, then the proposed message in a panel. Renames show
both paths; binary files show `-` for unknown line counts.

Press one key, without Enter:

- `a`: accept and print the selected message.
- `e`: type a replacement message and press Enter; an empty edit keeps it.
- `r`: regenerate the proposal.
- `q`: quit without selecting a message.

Accepting does not create a Git commit or change the index. Editing supports a
single line. The generator is deliberately a stub: it always returns
`chore: update staged files`, including after regeneration. The `Generator`
protocol in `cli.py` is the boundary for a future implementation.

Use `gitmsg --no-color` or set `NO_COLOR` (even to an empty value) to disable ANSI
styling. When stdout or stdin is not a terminal, gitmsg skips all UI and prints
only the message plus a newline:

```powershell
.\.venv\Scripts\gitmsg | Set-Content message.txt
```

Missing Git, running outside a working tree, and having nothing staged report
an error on stderr and exit with status 1. Successful selection or quit returns
0; interrupted input returns 130. No network requests or credentials are used.

## Build and test

```powershell
.\.venv\Scripts\python -m pip wheel --no-deps --wheel-dir dist .
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Packaging uses setuptools as a build tool. Tests use Python's standard library
and temporary Git repositories; they cover message-only output, errors, color
controls, staged metadata, and the interactive review actions.

## Authors

- [ItsLinkxy (itslinkdev)](https://github.com/itslinkdev): author and repository owner.
- Codex: co-author of the implementation.

Licensed under MIT; see [LICENSE](LICENSE).
