# Changelog

Changes are listed in implementation order. The links point to actual commits;
package version `0.1.0` identifies this early implementation, not a PyPI release.

## 0.1.0 development

1. [Staged review foundation](https://github.com/itslinkdev/gitmsg/commit/75f23f281c6c77b9572e54511cd1b6176eef6d6a)
   — CLI entry point, staged-file table, accept/edit/regenerate/quit loop,
   non-interactive output, tests, and MIT license.
2. [Offline generator](https://github.com/itslinkdev/gitmsg/commit/9821b50334c98ac5e513f9b35ee1d72128638377)
   — Conventional Commit heuristics, scope inference, ranked file summaries,
   and bounded staged-patch digest with streaming reads.
3. [Optional HTTPS provider](https://github.com/itslinkdev/gitmsg/commit/583dea91a1b194fd008d1b1f98e986e137987dad)
   — Anthropic over urllib, root TOML configuration, environment-only key,
   outbound filtering/redaction, exact payload preview, retry, and fallback.
4. [Git integration](https://github.com/itslinkdev/gitmsg/commit/6e01ef017ac6c7b1663c817a6a6ed90e09d12160)
   — Accepted-message commits, dry runs, explicit scripted acceptance, and
   non-destructive `prepare-commit-msg` installation with real Git tests.
5. [Continuous integration](https://github.com/itslinkdev/gitmsg/commit/e962bcb248f7fa68dd6ed7d03e1584be7f616e5c)
   — Ubuntu/Windows builds and tests on Python 3.11/3.13, plus usage and privacy docs.

## Repository documentation

- Reorganize the README around installation, review, commands, and configuration.
- Add detailed privacy documentation, a contributor code map, and offline-first
  example configuration.
- Include README, license, authors, and repository links in package metadata.
- Ignore local environment files and normalize source/documentation line endings.

## Validation fixes

- Compare installed hook files by filesystem identity so Windows temporary-path
  aliases (such as `RUNNER~1`) and their long names are treated as the same file.

The demo GIF is still a placeholder. HTTP tests are mocked; CI does not verify a
live provider account, model output quality, or macOS behavior.
