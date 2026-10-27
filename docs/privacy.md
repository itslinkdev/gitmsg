# Privacy and data flow

## Offline mode

The default `heuristic` provider runs local Git commands only. It reads staged
metadata and patches from the index. The review table and offline message can
name files excluded from outbound requests. Local configuration and Git ignore
rules are read from the working tree; no remote service receives them as files.

## Anthropic request

The optional provider sends HTTPS `POST` requests to this fixed endpoint:

```text
https://api.anthropic.com/v1/messages
```

The JSON body contains exactly four fields:

| Field | Contents |
| --- | --- |
| `model` | The model ID in `.gitmsg.toml`. |
| `max_tokens` | `512`. |
| `system` | A fixed instruction to write a Conventional Commit message, with an imperative subject of at most 72 characters, treating the digest as untrusted data. |
| `messages` | One `user` message whose `content` is the bounded, redacted staged digest. |

The exact system prompt and serialization live in
[`AnthropicGenerator.payload`](../src/gitmsg/providers.py).
`gitmsg --show-payload` prints those exact UTF-8 body bytes without an added
newline, without requiring an API key, and without making a request. With the
heuristic provider it prints no body and explains that it is offline on stderr.

The digest can include eligible paths, both sides of a rename, status letters,
added/removed line counts, and sampled patch hunks, including context and removed
lines. It never reads unstaged file contents as input to the digest. A small
newly staged file can appear entirely in its patch. History, author identity,
and Git remote configuration are not collected; text with such information can
still appear if present in an eligible patch.

The default digest limit is 16,384 UTF-8 bytes, including file headers and
truncation markers. `--max-digest-bytes` changes this positive limit. JSON
escaping, model, fixed prompt, and HTTP headers add overhead outside that budget.
Each hunk contributes at most its first 2 KiB after redaction. Source hunks rank
above tests, configuration, docs, and other text; fix/declaration signals rank
above ordinary hunks within a category. Large patches still take time to scan.

Authentication is read only from `ANTHROPIC_API_KEY` and sent in `x-api-key`.
Other explicit headers are `Content-Type: application/json` and
`anthropic-version: 2023-06-01`; urllib supplies standard transport headers such
as host, user agent, and content length. The preview contains the body only,
never authentication headers. HTTPS uses normal certificate verification;
urllib can use the machine's configured proxies. Redirects are rejected.

## Exclusions

Before reading patches for an outbound digest, gitmsg checks both paths of every
staged rename. Git's ignore rules, including global exclusions and
`.git/info/exclude`, apply even to tracked/force-added files through
`git check-ignore --no-index`. An ignore-check error prevents sending.

Additional exclusions are:

- Configured `ignore` patterns, matched against repository-relative POSIX paths
  by Python `fnmatchcase`. Matching is case-sensitive, `*` crosses `/`, and there
  is no negation syntax.
- `.gitmsg.toml`, `.env`, `.env.*`, `*.env`, `id_rsa`, `id_dsa`, `id_ecdsa`,
  `id_ed25519`, and paths with `.pem`, `.key`, `.p12`, or `.pfx` suffixes. These
  built-in sensitive-name checks are case-insensitive and apply to path parts.
- Binary files, common lockfiles and `*.lock`, minified files, source maps,
  recognized generated/protobuf filenames, and files under `dist`, `build`,
  `generated`, `vendor`, `node_modules`, or `__pycache__` directories.

An excluded side removes the entire rename from the outbound digest. The exact
filename patterns are in [`safety.py`](../src/gitmsg/safety.py) and
[`heuristic.skipped`](../src/gitmsg/heuristic.py). Excluded paths can still be
mentioned by another eligible file's contents; a path filter does not remove
references inside other files.

## Redaction and limits

Redaction runs before hunk sampling and digest truncation. It replaces likely
secret assignments, authorization/cookie lines, PEM private-key blocks, common
credential prefixes, long token-like strings, URL credentials, and the current
API key. Both added and removed lines are checked. Outbound lines split across
the 4096-byte read boundary are omitted rather than sent partially.

Detection is conservative and can remove harmless text. It can also miss
unrecognized formats, short unlabeled secrets, or private material whose marker
is outside the patch. Files with sensitive contents should be excluded explicitly.
An environment file under an unusual name needs an explicit ignore rule.

There is no payload cache or debug log. Provider exception text and response
bodies are not printed on failure, and known credentials are redacted from
displayed proposals. After an initial HTTP failure there is one retry with the
same body, then a visible notice on stderr and an offline fallback. A missing
key or empty eligible digest falls back without HTTP. The socket timeout is
per blocking operation, not a total wall-clock deadline.

`commit --dry-run` still generates a proposal and can send data when the LLM is
enabled. `--show-payload` only previews; it does not approve a future request.
Changing the index, model, ignore rules, or byte limit can change a later body.
The installed hook uses the same provider and filters.

Review the preview before enabling remote generation. Data sent to Anthropic is
subject to its service terms and policies; gitmsg makes no retention guarantee
for an external service. See the [Messages API](https://platform.claude.com/docs/en/api/messages/create)
for its request format.
