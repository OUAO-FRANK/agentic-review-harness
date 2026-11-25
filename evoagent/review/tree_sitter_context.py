"""Extract source line spans with the installed Tree-sitter grammars."""

from __future__ import annotations

from functools import cache
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Language, Node


_JAVASCRIPT = ("tree_sitter_javascript", "language")
_TYPESCRIPT = ("tree_sitter_typescript", "language_typescript")
_GRAMMARS = {
    ".js": _JAVASCRIPT,
    ".jsx": _JAVASCRIPT,
    ".mjs": _JAVASCRIPT,
    ".cjs": _JAVASCRIPT,
    ".ts": _TYPESCRIPT,
    ".mts": _TYPESCRIPT,
    ".cts": _TYPESCRIPT,
    ".tsx": ("tree_sitter_typescript", "language_tsx"),
    ".go": ("tree_sitter_go", "language"),
}
_SYMBOL_NODES = {
    "function_declaration", "function_signature", "generator_function_declaration", "class_declaration",
    "method_definition", "abstract_class_declaration", "interface_declaration",
    "type_alias_declaration", "enum_declaration", "method_declaration", "type_declaration",
}
_FUNCTION_VALUES = {"arrow_function", "function_expression", "generator_function"}


@cache
def _language(module: str, factory: str) -> Language:
    from tree_sitter import Language

    return Language(getattr(import_module(module), factory)())


def _is_symbol(node: Node) -> bool:
    if node.type in _SYMBOL_NODES:
        return True
    if node.type == "export_statement":
        value = node.child_by_field_name("value")
        return value is not None and value.type in _FUNCTION_VALUES
    if node.type in {"lexical_declaration", "variable_declaration"}:
        values = (child.child_by_field_name("value") for child in node.named_children)
        return any(value is not None and value.type in _FUNCTION_VALUES for value in values)
    return False


def _line_span(node: Node) -> tuple[int, int]:
    start = node.start_point.row + 1
    end_row, end_column = node.end_point
    return start, max(start, end_row + (end_column > 0))


def _symbol_span(node: Node) -> tuple[int, int]:
    parent = node.parent
    if parent is not None and parent.type == "ambient_declaration":
        node = parent
        parent = node.parent
    if parent is not None and parent.type == "export_statement":
        return _line_span(parent)
    start, end = _line_span(node)
    if node.type == "method_definition":
        sibling = node.prev_named_sibling
        while sibling is not None and sibling.type in {"decorator", "comment"}:
            if sibling.type == "decorator":
                start = sibling.start_point.row + 1
            sibling = sibling.prev_named_sibling
    return start, end


def tree_sitter_spans(source: str, suffix: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    grammar = _GRAMMARS.get(suffix)
    if grammar is None:
        return [], []

    try:
        from tree_sitter import Parser

        root = Parser(_language(*grammar)).parse(source.encode("utf-8")).root_node
    except (ImportError, OSError, RuntimeError, ValueError):
        return [], []
    if root.has_error:
        return [], []

    imports = [
        _line_span(node) for node in root.named_children
        if node.type in {"import_statement", "import_alias", "import_declaration"}
    ]
    symbols = []
    pending = list(root.named_children)
    while pending:
        node = pending.pop()
        if _is_symbol(node):
            symbols.append(_symbol_span(node))
        pending.extend(node.named_children)
    return symbols, imports
