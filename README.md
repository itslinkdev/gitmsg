# gitmsg

A small Python 3.11+ CLI that proposes Conventional Commit messages offline
for staged Git changes.
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
single line. Regeneration runs the same deterministic heuristic; unchanged
staged input produces the same proposal. The `Generator` protocol in `cli.py`
remains the boundary for another generator.

## Offline generator

The generator parses NUL-separated `git diff --cached --numstat` and
`--name-status` output, preserving both rename paths, deletions, and binary
line counts. It reads staged patches, never unstaged file contents.

- Documentation and test paths select `docs` and `test`; build manifests and
  CI paths select `build` and `ci`.
- New source files or added declarations select `feat`. Changes with added
  fix/bug markers, null guards, or exception handling select `fix`.
- Source renames, deletions, and other implementation edits select `refactor`;
  remaining changes fall back to `chore`. Source changes take precedence over
  accompanying docs, tests, build files, and lockfiles. Without source changes,
  precedence is `ci`, `build`, `test`, `docs`, then `chore`.
- Scope is the shared top-level directory of all staged paths, including both
  rename paths. Root files, mixed directories, unsupported scope punctuation,
  or a scope too long to leave room for an imperative subject omit the scope.
- Generated subjects start with an imperative verb and contain at most 72
  characters, including the type and scope. The body has up to five file bullets,
  ranked by source/test/config/docs priority, then changed-line count. Binary
  and excluded files remain eligible for the metadata summary.

Example:

```text
feat(src): add src/greet.py

- Add src/greet.py (+2/-0)
```

## Bounded digest

`gitmsg.heuristic.build_digest(files, max_bytes=16384)` builds a staged text
digest for the heuristic and a future LLM integration. The offline generator
samples source files for content inference; the digest function can summarize
all eligible staged files. No LLM is called.
Set the limit in UTF-8 **bytes**, including headers and truncation markers:

```powershell
.\.venv\Scripts\gitmsg --max-digest-bytes 8192
```

The value must be a positive integer. Binary files, common lockfiles, `.min.*`
files, source maps, generated filename patterns (such as `.generated.*`, `.g.*`,
and protobuf outputs), and files inside `dist`, `build`, `generated`, `vendor`,
`node_modules`, or `__pycache__` directories are excluded from the digest.

Patches stream from Git, including very long lines; the full patch is never
captured in memory. Candidate text is bounded by the digest budget. Source
hunks outrank tests, configuration, docs, and other text. Within a category,
fix markers and declarations outrank ordinary hunks, followed by file change
count and stable input order. Each hunk keeps at most its first 2 KiB before
the global byte limit is applied. Truncation is marked when space permits.

These are deliberately conservative path/content heuristics, not semantic
analysis: unusual file layouts or generated files without recognizable names
may be misclassified. Signals beyond a sampled hunk or the digest limit may be
missed, and scanning a huge patch still takes time. Review the proposed message.

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
controls, staged metadata, and the interactive review actions. Generator tests
cover docs-only, tests-only, new feature, rename, delete, lockfile-only, huge diff,
and binary-file scenarios, plus fix/refactor/build/CI inference, byte limits,
hunk priority, significant-file selection, literal paths, and staged-only reads.

## Authors

- [ItsLinkxy (itslinkdev)](https://github.com/itslinkdev): author and repository owner.
- Codex: co-author of the implementation.

Licensed under MIT; see [LICENSE](LICENSE).
