"""Select files that can be reviewed as source or project controls."""

from .types import ChangeSet, ChangedFile


_EXCLUDED_DIRS = {
    ".git", "__pycache__", "build", "dist", "generated", "node_modules", "vendor"
}
_BINARY_EXTENSIONS = {
    ".7z", ".class", ".dll", ".exe", ".gif", ".ico", ".jar", ".jpeg",
    ".jpg", ".pdf", ".png", ".pyc", ".so", ".webp", ".zip"
}
_LOCKFILES = {"package-lock.json", "pnpm-lock.yaml", "poetry.lock", "yarn.lock"}


class ChangePlanner:
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
