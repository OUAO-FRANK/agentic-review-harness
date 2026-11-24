"""Immutable inputs and identities for a review run."""

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

from ..diff_parser import parse_unified_diff


_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class ChangedFile:
    path: str
    added_lines: tuple[int, ...]


@dataclass(frozen=True)
class ChangeSet:
    base_sha: str
    head_sha: str
    files: tuple[ChangedFile, ...]

    @classmethod
    def from_diff(cls, diff: str, base_sha: str, head_sha: str) -> "ChangeSet":
        if not _SHA.fullmatch(base_sha) or not _SHA.fullmatch(head_sha):
            raise ValueError("base_sha and head_sha must be 40-character hex SHAs")
        paths: list[str] = []
        old_path = ""
        for line in diff.splitlines():
            if line.startswith("--- "):
                old_path = line[4:].strip()
            elif line.startswith("+++ "):
                new_path = line[4:].strip()
                path = old_path if new_path == "/dev/null" else new_path
                if path.startswith(("a/", "b/")):
                    path = path[2:]
                if not path or path == "/dev/null" or path in paths:
                    raise ValueError("diff contains an invalid or duplicate path")
                paths.append(path)
        added: dict[str, list[int]] = {path: [] for path in paths}
        for line in parse_unified_diff(diff).added_lines:
            if line.path in added:
                added[line.path].append(line.line)
        return cls(base_sha.lower(), head_sha.lower(), tuple(
            ChangedFile(path, tuple(added[path])) for path in paths
        ))

    def file(self, path: str) -> ChangedFile:
        return next(item for item in self.files if item.path == path)


@dataclass(frozen=True)
class ReviewGroup:
    group_id: str
    head_sha: str
    paths: tuple[str, ...]
    reason: str
    token_budget: int = 0
    estimated_tokens: int = 0

    @classmethod
    def from_paths(
        cls, change: ChangeSet, paths: Iterable[str], reason: str,
        token_budget: int = 0, estimated_tokens: int = 0,
    ) -> "ReviewGroup":
        selected = tuple(paths)
        if not selected or len(selected) != len(set(selected)):
            raise ValueError("review group paths must be nonempty and unique")
        known = {item.path for item in change.files}
        if not set(selected) <= known:
            raise ValueError("review group contains a path outside the change set")
        if not reason:
            raise ValueError("review group reason is required")
        ordered = tuple(sorted(selected))
        identity = hashlib.sha256(
            (change.head_sha + "\0" + "\0".join(ordered)).encode("utf-8")
        ).hexdigest()[:16]
        return cls(identity, change.head_sha, ordered, reason, token_budget, estimated_tokens)
