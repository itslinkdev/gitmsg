# gitmsg

[![CI](https://github.com/itslinkdev/gitmsg/actions/workflows/ci.yml/badge.svg)](https://github.com/itslinkdev/gitmsg/actions/workflows/ci.yml)

Review your staged changes, get a Conventional Commit message, and decide what
to commit. Works offline by default, with an optional Anthropic provider.

- **Review first.** Inspect file changes, edit the proposal, regenerate, or quit.
- **Keep it local.** The heuristic generator needs neither an API key nor a network connection.
- **Inspect outbound data.** Preview the exact redacted LLM request with `--show-payload`.
- **Use your Git workflow.** Print a message, commit it, or install a hook for your editor.

Python 3.11+ and Git on `PATH` are required. `rich` is the only runtime dependency;
HTTPS uses Python's standard-library `urllib`.

## Quick start

Install from this repository in a virtual environment.

### Windows / PowerShell

```powershell
git clone https://github.com/itslinkdev/gitmsg.git
cd gitmsg
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use `.\.venv\Scripts\gitmsg.exe` directly.

### Linux / macOS

```sh
git clone https://github.com/itslinkdev/gitmsg.git
cd gitmsg
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

With the environment active, enter any Git working tree and stage your changes:

```sh
git add src/greet.py
gitmsg
```

For a new `src/greet.py` containing one line, the offline proposal looks like:

```text
feat(src): add src/greet.py

- Add src/greet.py (+1/-0)
```

In a terminal, press `a` to accept, `e` to edit a single line, `r` to regenerate,
or `q` to quit. Accepting plain `gitmsg` prints the message. With unchanged input,
the offline generator produces the same result on regeneration.

> **Demo GIF placeholder:** a recording of review, payload inspection, and
> `gitmsg commit --dry-run` will go in `docs/demo.gif`.
<!-- Replace the placeholder with ![gitmsg demo](docs/demo.gif) when recorded. -->

## Commands

| Command | Result |
| --- | --- |
| `gitmsg` or `gitmsg generate` | Review and print a proposed message. |
| `gitmsg commit` | Review, then run `git commit -F` with the accepted message. |
| `gitmsg commit --dry-run` | Preview a proposal without creating a commit. |
| `gitmsg commit --yes` | Accept the proposal without interactive review. |
| `gitmsg --show-payload` | Print the exact LLM JSON body without sending it. |
| `gitmsg install-hook --dry-run` | Show the hook location without installing it. |
| `gitmsg install-hook` | Install `prepare-commit-msg`; refuse an existing hook. |

Use `--max-digest-bytes 8192` to lower the default 16 KiB digest limit, and
`--no-color` or `NO_COLOR` to disable ANSI styling. `gitmsg --help` lists all flags.

Piped/non-interactive `gitmsg` prints only the proposal, plus a newline. A
non-interactive `commit` requires `--yes`, `--dry-run`, or `--show-payload`.
Dry runs can still contact the configured LLM; `--show-payload` never does.

The CLI leaves staging to you and does not push, change your Git identity, or
disable signing. Accepted commit text is stored in a temporary UTF-8 file, then
removed even if Git fails. Existing Git hooks still run.

Exit codes: `0` for success or quit, `1` for repository/configuration/commit
errors, `2` for invalid arguments, and `130` for interrupted input.

## Configuration

No config file is needed for offline use. To customize a repository, copy
[`.gitmsg.example.toml`](.gitmsg.example.toml) to `.gitmsg.toml` at its root.
The CLI also finds that root config when invoked from a subdirectory.

```toml
[gitmsg]
provider = "heuristic"
timeout = 10
ignore = ["private/*", "internal/**"]
```

For LLM generation, change `provider` to `"anthropic"` and set `model` to a model
ID available to your API account. See Anthropic's [model IDs](https://platform.claude.com/docs/en/models/overview).
Load `ANTHROPIC_API_KEY` into your environment using your secret manager;
credentials never belong in this config file.

| Setting | Default | Meaning |
| --- | --- | --- |
| `provider` | `"heuristic"` | `heuristic` or `anthropic`. |
| `model` | unset | Required for Anthropic; passed to its Messages API. |
| `timeout` | `10` | Socket timeout in seconds per HTTP attempt; greater than 0, at most 120. |
| `ignore` | `[]` | Extra outbound exclusions using case-sensitive `fnmatchcase` patterns. |

Ignore patterns match repository-relative paths with `/` separators. `*` also
matches slashes, so `private/*` excludes all descendants. Negation is unsupported.
These rules control outbound LLM data; excluded paths can still appear in the
local review table and offline message.

A missing key or empty eligible digest selects the heuristic with a notice on
stderr. Network, HTTP, and invalid-response failures get one retry, then the
same fallback. Regenerating with Anthropic enabled makes another request.

## Privacy

The heuristic makes no HTTP requests. Anthropic receives one bounded, redacted
digest of eligible **staged** patches, plus the configured model, a fixed system
prompt, and `max_tokens=512`. Paths, status, line counts, removed lines, and
context can appear in that digest. A small staged file can fit in full.

Git ignores and configured exclusions are applied before reading outbound
patches. `.env` and private-key paths are excluded; likely credentials are
redacted before sampling and truncation. This is heuristic protection: inspect
`gitmsg --show-payload` and exclude sensitive paths before enabling the LLM.
The API key is sent only in the authentication header and is never printed.

See [Privacy and data flow](docs/privacy.md) for the exact body, headers,
exclusion rules, and detection limits.

## Git hook

The installed `prepare-commit-msg` hook inserts a proposal into an empty or
comment-only message for ordinary `git commit`, then Git opens your editor.
It preserves existing text and skips `-m`, `-F`, amend, merge, squash, and template
messages. It uses the same provider and privacy rules with a 16 KiB digest.
Generation errors leave the message alone with a notice.

Installation respects `core.hooksPath` and linked worktrees. Even an empty
existing hook is never overwritten. The hook invokes the Python interpreter
used during installation; keep that environment in place. If you move it,
remove the generated hook and reinstall. To uninstall, remove only the
`prepare-commit-msg` file created by gitmsg at the reported location. A shared
`core.hooksPath` affects every repository using that directory.

## Development

After installing and activating the environment above:

```sh
python -m unittest discover -s tests -v
python -m pip wheel --no-deps --wheel-dir dist .
git diff --check
```

Tests use temporary Git repositories and mocked HTTP only. CI builds and tests
on Ubuntu and Windows with Python 3.11 and 3.13. See
[Contributing](CONTRIBUTING.md) for the code map and development workflow, and
[Changelog](CHANGELOG.md) for the implementation sequence.

The generator uses path/content heuristics and samples at most 2 KiB per hunk;
it can miss intent in large or unusual changes. LLM proposals also need review.
Live API behavior and macOS are not exercised by CI.

## Authors and license

[ItsLinkxy (itslinkdev)](https://github.com/itslinkdev) is the repository owner.
Codex contributed to the implementation and documentation.

Licensed under [MIT](LICENSE).
