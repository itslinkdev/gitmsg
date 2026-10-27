# gitmsg

A small Python 3.11+ CLI that proposes Conventional Commit messages
for staged Git changes. The default heuristic provider works entirely offline;
an optional Anthropic provider uses HTTPS through Python's `urllib`.
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

Accepting plain `gitmsg` does not create a Git commit or change the index. Editing supports a
single line. Regeneration runs the same deterministic heuristic; unchanged
staged input produces the same proposal. The `Generator` protocol in
`providers.py` remains the boundary for another generator.

## Commit and hook integration

```powershell
gitmsg commit                 # Review, edit/regenerate, then accept to commit
gitmsg commit --dry-run       # Preview; never create a commit
gitmsg commit --yes           # Explicitly accept the proposal, useful in scripts
gitmsg install-hook --dry-run # Preview the hook location
gitmsg install-hook           # Install prepare-commit-msg; refuse any existing hook
```

`commit` writes the accepted message to a temporary UTF-8 file and runs
`git commit -F <file>`; the file is removed even on failure. Quit or interrupted
review leaves the index and history alone. Normal Git hooks still run. The
command does not stage, push, change identity or disable signing. A piped or
non-interactive commit requires `--yes`; `--dry-run` prints the proposal without
requiring acceptance. Dry runs can contact the configured LLM; use
`--show-payload` to inspect the body without any HTTP.

The installed hook fills an empty/comment-only message for an ordinary
`git commit`, then lets Git open your editor. It skips `-m`, `-F`, amend, merge,
squash and template messages, and preserves existing text. The hook uses the
configured provider, the same privacy filters, and a 16 KiB digest. Generation
errors leave the message unchanged with a notice, so Git can open your editor.

Installation respects `core.hooksPath` (which may be shared with other repos)
and linked worktrees. It creates an executable hook exclusively; even an empty
existing hook is never replaced. It uses Git's shell and the absolute Python
interpreter used at installation. Keep that environment installed; reinstall
the hook manually if you move/delete it. Remove only the generated hook to
uninstall. Hook behavior follows [Git's hook documentation](https://git-scm.com/docs/githooks).

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
digest for the heuristic and optional LLM integration. The offline generator
samples source files for content inference; the digest function can summarize
all eligible staged files.
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
0; interrupted input returns 130. The default provider uses no network or credentials.

## Optional LLM provider

Create `.gitmsg.toml` at the repository root (never put a key in it):

```toml
[gitmsg]
provider = "anthropic" # Default: "heuristic"
model = "claude-sonnet-4-5" # Choose an available model for your account
timeout = 10 # Seconds per attempt, > 0 and <= 120
ignore = ["private/*", "internal/**"]
```

Set `ANTHROPIC_API_KEY` in your environment using your secret manager, then run
`gitmsg` normally. The key is read only from this variable. A missing key or
empty eligible digest selects the heuristic with a notice on stderr. Network,
HTTP and invalid-response failures get one retry, then the same offline fallback.
Regenerating makes a new request when the LLM is enabled.

## Privacy

`gitmsg --show-payload` prints the exact UTF-8 JSON request body, with no extra
newline, and exits without HTTP or requiring a key. For the heuristic it prints
no body and reports that the provider is offline on stderr.

Only the following are sent to `https://api.anthropic.com/v1/messages`:

- The configured model, `max_tokens=512`, a fixed commit-writing system prompt,
  and one user message containing the bounded, redacted staged digest.
- That digest contains eligible paths (including rename paths), status and line
  counts, and sampled staged patch hunks, including removed and context lines.
  Its limit defaults to 16 KiB before JSON escaping; JSON and the fixed prompt
  add overhead. No full file, unstaged content, history, remote URL or author
  identity is included.
- HTTP headers contain `Content-Type: application/json`, `anthropic-version:
  2023-06-01` and the API key in `x-api-key`, plus standard urllib transport
  headers. `--show-payload` previews the body only; credentials are never printed.

The provider uses Git ignore rules, including global ignores and
`.git/info/exclude`, even for tracked/force-added files (`check-ignore --no-index`).
It also excludes the digest's generated/binary/lockfile paths, `.gitmsg.toml`,
`.env`, `.env.*`, `*.env`, private-key filenames and `.pem/.key/.p12/.pfx` files.
Either excluded side removes a whole rename. Config `ignore` patterns match
repository-relative POSIX paths using Python `fnmatchcase`: case-sensitive,
`*` matches slashes, no negation; `private/*` covers all descendants.

Before digest sampling/truncation, secret assignments, authorization/cookie
lines, PEM private-key blocks, known credential prefixes, long token-like
strings, URL credentials and the current API key are redacted. Lines longer
than 4096 bytes are omitted in outbound digests. Redirects are rejected. Provider
errors are reported without response bodies or exception text; keys are not logged.

Redaction is heuristic: unknown formats and short, unlabeled secrets may escape
detection. Exclude sensitive paths and inspect `--show-payload` before enabling
the LLM. Eligible code is sent to Anthropic and is subject to its data policies.
Local heuristic output and the local review table can still name excluded files.

API format: [Anthropic Messages documentation](https://platform.claude.com/docs/en/api/messages/create).

## Demo

TODO: add `docs/demo.gif` showing staged review and payload inspection.

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
