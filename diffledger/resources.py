"""Locate distributed assets in an installed wheel or source checkout."""
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parent


def resource_directory(name: str) -> Path:
    bundled = _PACKAGE / "assets" / name
    if bundled.is_dir():
        return bundled
    return _PACKAGE.parent / name
