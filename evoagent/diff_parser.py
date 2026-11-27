import codecs
import re
from collections.abc import Iterator
from dataclasses import dataclass
from io import StringIO
from typing import List

from .models import ChangedLine


@dataclass
class ParsedDiff:
    files: List[str]
    added_lines: List[ChangedLine]


HUNK_HEADER = re.compile(
    r"^@@\s+-(?P<old>\d+)(?:,(?P<old_count>\d+))?\s+"
    r"\+(?P<new>\d+)(?:,(?P<new_count>\d+))?\s+@@(?P<label>.*)$"
)
_NO_NEWLINE = "\\ No newline at end of file"


def file_header_path(header: str) -> str:
    """Return the repository path from a --- or +++ header, retaining /dev/null."""
    value = header[4:].split("\t", 1)[0]
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        try:
            value = codecs.escape_decode(value[1:-1].encode("utf-8"))[0].decode("utf-8")
        except (ValueError, UnicodeError):
            # Keep Git's printable spelling when the filename is not UTF-8 text.
            return value
    return value.removeprefix("a/" if header.startswith("--- ") else "b/")


def iter_diff_lines(diff: str, *, strict: bool = False) -> Iterator[tuple[str, str]]:
    """Separate patch headers from hunk body lines that happen to look like headers."""
    in_hunk = False
    old_remaining = new_remaining = 0
    pending_file = active_file = False
    for position, line in enumerate(StringIO(diff, newline=None), 1):
        raw = line.removesuffix("\n")
        if in_hunk:
            if raw == _NO_NEWLINE:
                yield "body", raw
                continue
            old_line = int(raw.startswith((" ", "-")))
            new_line = int(raw.startswith((" ", "+")))
            file_header = raw.startswith(("--- ", "+++ "))
            if (old_line or new_line) and (
                (old_line <= old_remaining and new_line <= new_remaining)
                or (not strict and not file_header)
            ):
                old_remaining = max(0, old_remaining - old_line)
                new_remaining = max(0, new_remaining - new_line)
                yield "body", raw
                continue
            if strict and (
                old_remaining or new_remaining
                or ((old_line or new_line) and not raw.startswith("--- "))
            ):
                raise ValueError(f"invalid unified diff hunk at input line {position}")
            in_hunk = False
            old_remaining = new_remaining = 0

        if raw.startswith("diff --git "):
            if strict and pending_file:
                raise ValueError(f"incomplete unified diff file headers at input line {position}")
            pending_file = active_file = False
            yield "boundary", raw
        elif raw.startswith("--- "):
            if strict and pending_file:
                raise ValueError(f"incomplete unified diff file headers at input line {position}")
            pending_file, active_file = True, False
            yield "old-file", raw
        elif raw.startswith("+++ "):
            if strict and not pending_file:
                raise ValueError(f"missing unified diff old file header at input line {position}")
            pending_file, active_file = False, True
            yield "new-file", raw
        elif match := HUNK_HEADER.match(raw):
            if strict and not active_file:
                raise ValueError(f"missing file headers for unified diff hunk at input line {position}")
            old_remaining = int(match["old_count"] or "1")
            new_remaining = int(match["new_count"] or "1")
            in_hunk = True
            yield "hunk", raw
        elif strict and raw.startswith("@@"):
            raise ValueError(f"malformed unified diff hunk header at input line {position}")

    if strict and (old_remaining or new_remaining):
        raise ValueError("truncated unified diff hunk at end of input")
    if strict and pending_file:
        raise ValueError("incomplete unified diff file headers at end of input")


def parse_unified_diff(diff: str) -> ParsedDiff:
    files: List[str] = []
    added: List[ChangedLine] = []
    current_path = ""
    new_line = 0
    for kind, raw in iter_diff_lines(diff):
        if kind == "boundary":
            current_path = ""
        elif kind == "new-file":
            current_path = file_header_path(raw)
            if current_path != "/dev/null" and current_path not in files:
                files.append(current_path)
        elif kind == "hunk":
            match = HUNK_HEADER.match(raw)
            assert match is not None
            new_line = int(match["new"])
        elif kind == "body":
            if raw.startswith("+"):
                added.append(ChangedLine(current_path or "unknown", new_line, raw[1:]))
            if raw.startswith(("+", " ")):
                new_line += 1

    return ParsedDiff(files=files, added_lines=added)

