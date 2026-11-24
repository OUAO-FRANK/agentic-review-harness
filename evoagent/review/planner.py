"""Select files that can be reviewed as source or project controls."""

from .types import ChangeSet, ChangedFile, ReviewGroup


_EXCLUDED_DIRS = {
    ".git", "__pycache__", "build", "dist", "generated", "node_modules", "vendor"
}
_BINARY_EXTENSIONS = {
    ".7z", ".class", ".dll", ".exe", ".gif", ".ico", ".jar", ".jpeg",
    ".jpg", ".pdf", ".png", ".pyc", ".so", ".webp", ".zip"
}
_LOCKFILES = {"package-lock.json", "pnpm-lock.yaml", "poetry.lock", "yarn.lock"}


class ChangePlanner:
    def __init__(self, max_files: int = 8, max_tokens: int = 8000):
        if max_files < 1 or max_tokens < 1:
            raise ValueError("max_files and max_tokens must be positive")
        self.max_files = max_files
        self.max_tokens = max_tokens

    @staticmethod
    def is_reviewable(path: str) -> bool:
        parts = path.replace("\\", "/").split("/")
        if not path or any(part in {"", ".", ".."} for part in parts):
            return False
        if any(part.lower() in _EXCLUDED_DIRS for part in parts[:-1]):
            return False
        filename = parts[-1].lower()
        if filename in _LOCKFILES or filename == "generated.py" or filename.endswith(".lock"):
            return False
        return not any(filename.endswith(ext) for ext in _BINARY_EXTENSIONS)

    def reviewable_files(self, change: ChangeSet) -> tuple[ChangedFile, ...]:
        return tuple(sorted(
            (item for item in change.files if self.is_reviewable(item.path)),
            key=lambda item: item.path,
        ))

    @staticmethod
    def _estimate(file: ChangedFile) -> int:
        return 32 * max(1, len(file.added_lines))

    def plan(self, change: ChangeSet) -> tuple[ReviewGroup, ...]:
        files = self.reviewable_files(change)
        remaining = {item.path: item for item in files}
        groups: list[ReviewGroup] = []

        def emit(items: list[ChangedFile], reason: str) -> None:
            groups.append(ReviewGroup.from_paths(
                change, (item.path for item in items), reason,
                token_budget=self.max_tokens,
                estimated_tokens=sum(self._estimate(item) for item in items),
            ))

        # Keep a changed source and its directly named test together when possible.
        if self.max_files >= 2:
            for source in files:
                if source.path not in remaining or source.path.startswith("tests/"):
                    continue
                stem = source.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                matches = [item for item in files if item.path in remaining
                           and item.path.startswith("tests/")
                           and item.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                           in {"test_" + stem, stem + "_test"}]
                if matches and self._estimate(source) + self._estimate(matches[0]) <= self.max_tokens:
                    pair = [source, matches[0]]
                    emit(pair, "source-and-test")
                    for item in pair:
                        del remaining[item.path]

        bucket: list[ChangedFile] = []
        bucket_tokens = 0
        bucket_dir = ""
        for item in remaining.values():
            cost = self._estimate(item)
            directory = item.path.rsplit("/", 1)[0] if "/" in item.path else ""
            if bucket and (directory != bucket_dir or len(bucket) == self.max_files
                           or bucket_tokens + cost > self.max_tokens):
                emit(bucket, "module")
                bucket, bucket_tokens = [], 0
            if cost > self.max_tokens:
                emit([item], "oversized-file")
                continue
            bucket.append(item)
            bucket_tokens += cost
            bucket_dir = directory
        if bucket:
            emit(bucket, "module")
        return tuple(sorted(groups, key=lambda group: group.paths[0]))
