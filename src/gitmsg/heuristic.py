"""Deterministic, offline commit messages and a byte-bounded staged digest."""

import re
from collections.abc import Sequence
from pathlib import PurePosixPath

from .git import StagedFile, patch_hunks
from .safety import Redactor


DEFAULT_MAX_DIGEST_BYTES = 16_384
SOURCE_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".c",
    ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".sh", ".sql",
    ".html", ".css", ".scss", ".vue", ".svelte",
}
LOCKFILES = {
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "uv.lock", "pipfile.lock", "cargo.lock", "gemfile.lock",
    "composer.lock", "go.sum", "packages.lock.json",
}
BUILD_FILES = {
    "pyproject.toml", "setup.py", "setup.cfg", "package.json", "cargo.toml",
    "go.mod", "makefile", "cmakelists.txt", "dockerfile", "build.gradle",
    "build.gradle.kts", "pom.xml", "gemfile", "composer.json", "tsconfig.json",
}
FIX = re.compile(
    r"\b(fix(?:es|ed)?|bug|regression|workaround|prevent|guard)\b"
    r"|\b(?:if|unless)\b.*(?:\bNone\b|\bnull\b|\bundefined\b|\bisinstance\b)"
    r"|\b(?:raise|except|throw|catch)\b", re.IGNORECASE,
)
DECLARATION = re.compile(
    r"^\s*(?:(?:export|public|async|static|default)\s+)*"
    r"(?:def|class|function|interface|enum|fn|func)\b"
)


def readable(text: str) -> str:
    return " ".join("".join(c if c.isprintable() else " " for c in text).split())


def skipped(file: StagedFile) -> bool:
    path = PurePosixPath(file.path.lower())
    return (
        file.binary or path.name in LOCKFILES or path.suffix == ".lock"
        or path.name.startswith(("generated.", "generated_"))
        or any(part in {"dist", "build", "generated", "vendor", "node_modules", "__pycache__"}
               for part in path.parts[:-1])
        or any(marker in path.name for marker in (".min.", ".generated.", ".gen.", ".g.", "_generated."))
        or path.name.endswith((".map", ".pb.go", ".pb.cc", ".pb.h", "_pb2.py", "_pb2_grpc.py", ".designer.cs"))
    )


def category(file: StagedFile) -> str:
    path = PurePosixPath(file.path.lower())
    name = path.name
    if skipped(file):
        return "chore"
    if (path.parts[:2] == (".github", "workflows") or ".circleci" in path.parts
            or name in {".gitlab-ci.yml", "jenkinsfile", "azure-pipelines.yml"}):
        return "ci"
    if (name in BUILD_FILES or name.startswith("requirements") and path.suffix == ".txt"
            or path.suffix in {".csproj", ".sln"}):
        return "build"
    if (any(part in {"test", "tests", "__tests__"} for part in path.parts[:-1])
            or name.startswith("test_") or re.search(r"(?:[._](?:test|spec))\.", name)
            or name.endswith("_test.go")):
        return "test"
    if (any(part in {"doc", "docs"} for part in path.parts[:-1])
            or path.suffix in {".md", ".rst", ".txt", ".adoc"}
            or name in {"license", "copying"}):
        return "docs"
    return "source" if path.suffix in SOURCE_SUFFIXES else "chore"


def significance(file: StagedFile) -> tuple[int, int]:
    priority = {"source": 5, "test": 4, "ci": 3, "build": 3, "docs": 2, "chore": 1}
    return priority[category(file)], file.changes


def clip_bytes(text: str, limit: int) -> str:
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    marker = b"\n[truncated]\n"
    if limit < len(marker):
        return data[:limit].decode("utf-8", errors="ignore")
    return data[:limit - len(marker)].decode("utf-8", errors="ignore") + marker.decode()


def hunk_priority(hunk: str) -> int:
    added = "\n".join(line[1:] for line in hunk.splitlines() if line.startswith("+"))
    if FIX.search(added):
        return 2
    return int(any(DECLARATION.search(line) for line in added.splitlines()))


def build_digest(files: Sequence[StagedFile], max_bytes: int = DEFAULT_MAX_DIGEST_BYTES, *, safe: bool = False) -> str:
    """Keep higher-priority files/hunks first and cap the UTF-8 result size."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    candidates = []
    order = 0
    for file in sorted(files, key=significance, reverse=True):
        if skipped(file) or (safe and file.old_path and skipped(StagedFile(file.status, file.old_path, file.added, file.removed))):
            continue
        header = f"# {readable(file.label)} [{file.status} +{file.added}/-{file.removed}]\n"
        if safe:
            header = Redactor()(header)
        # shortcut: keep each hunk's first 2 KiB; use syntax-aware sampling for semantic coverage.
        for hunk in patch_hunks(file, min(2048, max_bytes), Redactor() if safe else None):
            text = clip_bytes(header + hunk, max_bytes)
            rank = (significance(file)[0], hunk_priority(hunk), file.changes, -order)
            candidates.append((rank, text))
            order += 1
            candidates.sort(reverse=True)
            remaining = max_bytes
            bounded = []
            for priority, candidate in candidates:
                if remaining <= 0:
                    break
                candidate = clip_bytes(candidate, remaining)
                if not candidate:
                    continue
                bounded.append((priority, candidate))
                remaining -= len(candidate.encode("utf-8"))
            candidates = bounded
    return "".join(text for _, text in candidates)


def infer_type(files: Sequence[StagedFile], digest: str) -> str:
    kinds = {category(file) for file in files}
    source = [file for file in files if category(file) == "source"]
    if not source:
        return next((kind for kind in ("ci", "build", "test", "docs") if kind in kinds), "chore")
    if all(file.status in {"R", "D"} for file in source):
        return "refactor"
    if any(file.status == "A" for file in source):
        return "feat"
    added = [line[1:] for line in digest.splitlines() if line.startswith("+")]
    removed = {line[1:].strip() for line in digest.splitlines() if line.startswith("-")}
    if any(FIX.search(line) for line in added):
        return "fix"
    if any(DECLARATION.search(line) and line.strip() not in removed for line in added):
        return "feat"
    return "refactor"


def infer_scope(files: Sequence[StagedFile]) -> str:
    paths = [PurePosixPath(path) for file in files for path in (file.path, file.old_path) if path]
    tops = {path.parts[0] for path in paths if len(path.parts) > 1}
    if not paths or any(len(path.parts) < 2 for path in paths) or len(tops) != 1:
        return ""
    scope = tops.pop()
    return scope if re.fullmatch(r"[\w.-]+", scope) else ""


class HeuristicGenerator:
    def __init__(self, max_digest_bytes: int = DEFAULT_MAX_DIGEST_BYTES):
        if max_digest_bytes <= 0:
            raise ValueError("max_digest_bytes must be positive")
        self.max_digest_bytes = max_digest_bytes

    def generate(self, files: Sequence[StagedFile]) -> str:
        if not files:
            raise ValueError("At least one staged file is required")
        source = [file for file in files if category(file) == "source"]
        digest = build_digest(source, self.max_digest_bytes)
        kind = infer_type(files, digest)
        scope = infer_scope(files)
        ranked = sorted(files, key=significance, reverse=True)
        statuses = {file.status for file in files}
        verb = {"feat": "add", "fix": "fix", "refactor": "refactor"}.get(kind, "update")
        if statuses == {"R"}:
            verb = "rename"
        elif statuses == {"D"}:
            verb = "remove"
        prefix = f"{kind}({scope}): " if scope else f"{kind}: "
        if len(prefix) + len(verb) + 2 > 69:
            prefix = f"{kind}: "
        target = readable(ranked[0].path) if len(files) == 1 else {
            "feat": "functionality", "fix": "behavior", "docs": "documentation",
            "test": "tests", "build": "build configuration", "ci": "CI configuration",
            "refactor": "implementation", "chore": "staged files",
        }[kind]
        subject = prefix + verb + " " + target
        if len(subject) > 72:
            subject = subject[:69].rstrip() + "..."
        bullets = []
        for file in ranked[:5]:
            action = {"A": "Add", "D": "Remove", "R": "Rename", "C": "Copy"}.get(file.status, "Update")
            counts = "binary" if file.binary else f"+{file.added}/-{file.removed}"
            bullets.append(f"- {action} {readable(file.label)} ({counts})")
        return subject + "\n\n" + "\n".join(bullets)
