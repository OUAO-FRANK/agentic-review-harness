"""Plan scoped review work, run workers, then apply the existing finding gate."""

from collections import defaultdict
from dataclasses import dataclass

from ..diff_parser import ParsedDiff, iter_diff_lines
from ..gates import FindingGate, GateResult
from ..models import Finding
from .context import ContextBuilder
from .planner import ChangePlanner
from .types import ChangeSet, ContextBundle, ReviewGroup
from .workers import GroupWorkerPool


@dataclass(frozen=True)
class GroupReviewInput:
    group: ReviewGroup
    diff: str
    parsed: ParsedDiff
    context: ContextBundle | None


def _file_patches(diff: str) -> dict[str, str]:
    """Keep each hunk with its file, including text that looks like a file header."""
    sections: dict[str, list[str]] = defaultdict(list)
    old_header = ""
    current = None
    for kind, line in iter_diff_lines(diff, strict=True):
        if kind == "boundary":
            old_header, current = "", None
        elif kind == "old-file":
            old_header, current = line, None
        elif kind == "new-file":
            path = line[4:].strip().split("\t", 1)[0]
            if path == "/dev/null":
                path = old_header[4:].strip().split("\t", 1)[0]
            if path.startswith(("a/", "b/")):
                path = path[2:]
            current = sections[path]
            current.extend((old_header + "\n", line + "\n"))
            old_header = ""
        elif current is not None:
            current.append(line + "\n")
    return {path: "".join(lines) for path, lines in sections.items()}


class ReviewPipeline:
    def __init__(self, max_concurrent_groups: int = 2):
        self.planner = ChangePlanner()
        self.workers = GroupWorkerPool(max_concurrent_groups)

    def run(
        self, diff: str, parsed: ParsedDiff, worker_stage, gate: FindingGate,
        change: ChangeSet | None = None, repository_root: str = "",
    ) -> tuple[list[Finding], dict, list[dict], GateResult]:
        groups: dict[str, GroupReviewInput] | None = None
        gate_input = parsed
        if change is not None:
            patches = _file_patches(diff)
            builder = ContextBuilder(repository_root, change) if repository_root else None
            lines_by_path = defaultdict(list)
            for line in parsed.added_lines:
                lines_by_path[line.path].append(line)
            groups = {}
            for group in self.planner.plan(change):
                group_parsed = ParsedDiff(
                    list(group.paths), [line for path in group.paths for line in lines_by_path[path]],
                )
                groups[group.group_id] = GroupReviewInput(
                    group, "".join(patches.get(path, "") for path in group.paths), group_parsed,
                    builder.build(group) if builder else None,
                )
            gate_input = ParsedDiff(
                [path for scope in groups.values() for path in scope.parsed.files],
                [line for scope in groups.values() for line in scope.parsed.added_lines],
            )
        worker_diff = (
            "".join(scope.diff for scope in groups.values()) if groups is not None else diff
        )
        findings, collaboration, components = worker_stage(groups, worker_diff, gate_input)
        return findings, collaboration, components, gate.apply(findings, gate_input)
