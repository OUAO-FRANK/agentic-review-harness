"""Build auditable source context for a review group."""

import ast
import hashlib
from io import StringIO
from pathlib import Path

from ..context_manager import estimate_tokens
from ..repository_tools import read_repository_source
from .tree_sitter_context import tree_sitter_spans
from .types import ChangeSet, ContextBundle, ContextItem, ReviewGroup


def _enclosing_span(symbols: list[tuple[int, int]], line: int) -> tuple[int, int] | None:
    return next(((start, end) for start, end in symbols if start <= line <= end), None)


def _changed_symbol_spans(
    symbols: list[tuple[int, int]], changed_lines: list[int],
) -> dict[tuple[int, int], list[int]]:
    symbols.sort(key=lambda span: (span[1] - span[0], span[0]))
    changed_spans: dict[tuple[int, int], list[int]] = {}
    for line in changed_lines:
        span = _enclosing_span(symbols, line)
        if span is not None:
            changed_spans.setdefault(span, []).append(line)
    return changed_spans


def _python_spans(
    source: str, path: str, lines: list[str], changed_lines: list[int],
) -> tuple[dict[tuple[int, int], list[int]], list[tuple[int, int, str]]]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return {}, []

    nodes = list(ast.walk(tree))
    symbols = []
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno
            if node.decorator_list:
                start = node.decorator_list[0].lineno
                # A parenthesized decorator can start before its AST expression.
                while not lines[start - 1].lstrip().startswith("@"):
                    start -= 1
            symbols.append((start, node.end_lineno or node.lineno))
    changed_spans = _changed_symbol_spans(symbols, changed_lines)
    changed = set(changed_lines)
    names = {
        node.id for node in nodes
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        and (node.lineno in changed or any(start <= node.lineno <= end for start, end in changed_spans))
    }

    imports = []
    for node in nodes:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        referenced = any((alias.asname or alias.name.split(".")[0]) in names for alias in node.names)
        scope = _enclosing_span(symbols, node.lineno)
        if scope is None or (referenced and any(scope[0] <= line <= scope[1] for line in changed_lines)):
            reason = "direct-import" if referenced else "module-import"
            imports.append((node.lineno, node.end_lineno or node.lineno, reason))
    return changed_spans, imports


def _item(
    path: str, lines: list[str], start: int, end: int, reason: str, tool: str = "source-line",
) -> ContextItem:
    content = "".join(lines[start - 1:end])
    return ContextItem(
        path, start, end, content, reason, tool,
        estimate_tokens(content), hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


class ContextBuilder:
    """Read source snippets from the supplied checkout of the change's head."""

    def __init__(self, repository_root: str | Path, change: ChangeSet):
        self.root = Path(repository_root).resolve()
        self.change = change

    def build(self, group: ReviewGroup, token_budget: int | None = None) -> ContextBundle:
        """Apply the group limit and any tighter override to estimated source tokens."""
        files = {file.path: file for file in self.change.files}
        if group.head_sha != self.change.head_sha or not set(group.paths) <= files.keys():
            raise ValueError("review group must belong to the change set")
        if type(group.token_budget) is not int or group.token_budget < 0:
            raise ValueError("group token budget must be a nonnegative integer")
        budget = group.token_budget if token_budget is None else token_budget
        if type(budget) is not int or budget < 0:
            raise ValueError("token_budget must be a nonnegative integer")
        if group.token_budget:
            budget = min(budget, group.token_budget)

        items: list[ContextItem] = []
        seen: set[str] = set()
        total = 0

        def keep(item: ContextItem) -> bool:
            nonlocal total
            if item.content_hash in seen or any(
                previous.path == item.path
                and previous.start_line <= item.start_line
                and item.end_line <= previous.end_line
                for previous in items
            ):
                return True
            if total + item.estimated_tokens > budget:
                return False
            items.append(item)
            seen.add(item.content_hash)
            total += item.estimated_tokens
            return True

        fallback_lines: list[ContextItem] = []
        imports: list[ContextItem] = []
        for path in sorted(group.paths):
            if total == budget:
                break
            added = files[path].added_lines
            if not added:
                continue
            try:
                source = read_repository_source(self.root, path)
            except (OSError, ValueError, RuntimeError, SyntaxError):
                continue
            if "\x00" in source:
                continue
            lines = list(StringIO(source))
            changed_lines = sorted({line for line in added if 1 <= line <= len(lines)})
            if not changed_lines:
                continue
            suffix = Path(path).suffix.lower()
            if suffix == ".py":
                changed_spans, dependency_spans = _python_spans(source, path, lines, changed_lines)
                tool = "python-ast"
            else:
                symbols, module_imports = tree_sitter_spans(source, suffix)
                changed_spans = _changed_symbol_spans(symbols, changed_lines)
                dependency_spans = [(start, end, "module-import") for start, end in module_imports]
                tool = "tree-sitter"
            for (start, end), anchors in sorted(changed_spans.items()):
                if not keep(_item(path, lines, start, end, "changed-symbol", tool)):
                    fallback_lines.extend(_item(path, lines, line, line, "changed-line") for line in anchors)
            enclosed = {line for anchors in changed_spans.values() for line in anchors}
            fallback_lines.extend(
                _item(path, lines, line, line, "changed-line")
                for line in changed_lines if line not in enclosed
            )
            imports.extend(_item(path, lines, start, end, reason, tool) for start, end, reason in dependency_spans)

        for item in fallback_lines:
            keep(item)
        for item in sorted(imports, key=lambda item: (item.reason != "direct-import", item.path, item.start_line)):
            keep(item)
        return ContextBundle(group.group_id, group.head_sha, budget, total, tuple(items))
