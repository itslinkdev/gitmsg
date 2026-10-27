# Contributing

Keep changes small, readable, and supported by tests. Python 3.11+ and Git are
required. Follow the installation steps in the [README](README.md), then work
in the activated virtual environment. The existing runtime dependency is
`rich`; provider HTTPS and tests use the standard library.

## Workflow

1. Read the relevant module and its callers before editing.
2. Add a focused regression test for behavior changes. Use temporary Git
   repositories and mock HTTP; never use real API keys or live LLM requests.
3. Update the README/reference docs when commands, config, or data flow change.
4. Run the checks below, then commit one coherent change with an imperative
   message under 72 characters. Include Codex attribution when applicable.
5. Open a pull request describing the behavior change and validation.

```sh
python -m unittest discover -s tests -v
python -m pip wheel --no-deps --wheel-dir dist .
git diff --check
```

For focused work, select one suite:

```sh
python -m unittest discover -s tests -p test_providers.py -v
```

GitHub Actions installs the package, builds a wheel, and runs the full suite on
Ubuntu and Windows with Python 3.11 and 3.13. It needs no API credentials. A
passing mocked test does not establish live API availability or model quality.

## Code map

| File | Responsibility |
| --- | --- |
| `src/gitmsg/cli.py` | Parse commands and run review/accept/quit actions. |
| `src/gitmsg/ui.py` | Rich display and terminal key input. |
| `src/gitmsg/git.py` | Read staged metadata and stream staged patch hunks. |
| `src/gitmsg/heuristic.py` | Infer offline messages and build a bounded digest. |
| `src/gitmsg/config.py` | Load and validate root `.gitmsg.toml`. |
| `src/gitmsg/safety.py` | Filter outbound paths and redact likely secrets. |
| `src/gitmsg/providers.py` | Generator protocol, provider selection, HTTPS, retry/fallback. |
| `src/gitmsg/integration.py` | Commit accepted text and install a hook exclusively. |
| `src/gitmsg/hook.py` | Fill an ordinary empty Git message before the editor opens. |
| `tests/test_cli.py` | CLI output, errors, and interactive review. |
| `tests/test_heuristic.py` | Git metadata, classification, sampling, and byte limits. |
| `tests/test_providers.py` | Config, exact payloads, privacy, and mocked HTTP failures. |
| `tests/test_integration.py` | Real temporary-repo commits and hook behavior. |
| `tests/support.py` | Isolated repository setup with live HTTP blocked. |

## How generation works

The CLI asks Git for staged metadata, then selects a generator from config.
The heuristic infers type/scope and adds up to five ranked file bullets. Source
changes take precedence over docs, tests, build, CI, and lockfiles. Without
source changes, precedence is `ci`, `build`, `test`, `docs`, then `chore`.
Rename/delete-only source changes select `refactor`; added files/declarations
select `feat`, and added fix/guard/error-handling signals can select `fix`.
The heuristic subject is at most 72 characters, including type and optional scope.

The Anthropic generator filters paths, redacts while streaming patches, builds
the bounded digest, and serializes the request. The review loop presents the
result; accepting `commit` passes it to Git through a temporary message file.
The hook uses the same generator selection without running the interactive UI.

Keep outbound-data changes in the shared filtering/redaction path and update
[the privacy reference](docs/privacy.md). Reuse the `Generator` protocol for a
new provider, with a matching config choice and mocked tests. Do not add plugin
discovery or dependencies for a provider that can use the existing boundary.

## Scope and known limits

The project is an early CLI implementation. It does not stage files, push, or
manage credentials. The digest samples text rather than understanding an entire
codebase. Live API behavior, macOS, and provider message quality are outside the
current CI coverage. The demo GIF remains a documented placeholder.

Do not commit keys, local `.env` files, virtual environments, build output, or
local `AGENTS.md` instructions. The project is [MIT licensed](LICENSE).
