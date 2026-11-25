import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from evoagent.context_manager import estimate_tokens
from evoagent.review import ChangeSet, ChangedFile, ContextBuilder, ReviewGroup


class ContextBuilderTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "checkout"
        self.root.mkdir()

    def write(self, path, source):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")

    def context(self, changes, group_budget=0):
        files = tuple(ChangedFile(path, lines) for path, lines in changes.items())
        change = ChangeSet("a" * 40, "b" * 40, files)
        group = ReviewGroup.from_paths(change, changes, "test", token_budget=group_budget)
        return ContextBuilder(self.root, change), group

    def test_extracts_innermost_python_symbol_and_module_imports(self):
        imports = "from .helpers import (\n    transform as convert,\n)\n"
        method = "    @decorator\n    async def apply(self):\n        return convert('é\u2028x')\n"
        source = (
            imports + "\nclass Controller:\n" + method
            + "\ndef unrelated():\n    import hidden\n    return None\n"
        )
        self.write("pkg/main.py", source)
        builder, group = self.context({"pkg/main.py": (6, 8)})
        bundle = builder.build(group, token_budget=240)

        self.assertEqual((bundle.group_id, bundle.head_sha), (group.group_id, group.head_sha))
        self.assertEqual(
            [(item.path, item.start_line, item.end_line, item.content) for item in bundle.items],
            [("pkg/main.py", 6, 8, method), ("pkg/main.py", 1, 3, imports)],
        )
        self.assertEqual([item.reason for item in bundle.items], ["changed-symbol", "direct-import"])
        for item in bundle.items:
            self.assertTrue(item.tool)
            self.assertEqual(item.content_hash, hashlib.sha256(item.content.encode("utf-8")).hexdigest())
            self.assertEqual(item.estimated_tokens, estimate_tokens(item.content))

    def test_deduplicates_identical_content_and_preserves_priority(self):
        import_line = "import json\n"
        source = import_line + "def render():\n    return json.dumps({})\n"
        for path in ("b.py", "a.py"):
            self.write(path, source)
        builder, group = self.context({"b.py": (1, 2, 3), "a.py": (2, 3)})
        bundle = builder.build(group, token_budget=240)

        self.assertEqual([(item.path, item.content) for item in bundle.items], [
            ("a.py", source[len(import_line):]),
            ("b.py", import_line),
        ])
        self.assertEqual(len({item.content_hash for item in bundle.items}), 2)
        self.assertEqual(bundle.total_tokens, sum(estimate_tokens(item.content) for item in bundle.items))

    def test_exact_budget_prefers_changed_symbol_to_import(self):
        changed = "def fetch():\n    return pathlib.Path.cwd()\n"
        self.write("module.py", "import pathlib\n" + changed)
        builder, group = self.context({"module.py": (3,)}, group_budget=estimate_tokens(changed))

        bundle = builder.build(group, token_budget=240)
        self.assertEqual(bundle.token_budget, estimate_tokens(changed))
        self.assertEqual(bundle.total_tokens, bundle.token_budget)
        self.assertEqual([item.content for item in bundle.items], [changed])
        self.assertEqual(builder.build(group), bundle)
        self.assertEqual(builder.build(group, token_budget=0).items, ())

    def test_group_prefers_complete_symbols_over_fallback_lines_in_earlier_files(self):
        changed = "def run():\n    return 2\n"
        self.write("a.py", "value = 1\n")
        self.write("b.py", changed)
        builder, group = self.context({"a.py": (1,), "b.py": (2,)})

        bundle = builder.build(group, token_budget=estimate_tokens(changed))
        self.assertEqual([(item.path, item.content) for item in bundle.items], [("b.py", changed)])

    def test_oversized_symbol_keeps_only_whole_changed_lines_that_fit(self):
        changed = "    return '上下文'\n"
        self.write("module.py", "def fetch():\n    \"" + "长" * 100 + "\"\n" + changed)
        builder, group = self.context({"module.py": (2, 3)})
        budget = estimate_tokens(changed)
        bundle = builder.build(group, token_budget=budget)

        self.assertEqual([(item.start_line, item.end_line, item.content) for item in bundle.items],
                         [(3, 3, changed)])
        self.assertEqual(bundle.items[0].content_hash, hashlib.sha256(changed.encode("utf-8")).hexdigest())
        self.assertEqual(bundle.total_tokens, budget)
        below_limit = builder.build(group, token_budget=budget - 1)
        self.assertEqual((below_limit.items, below_limit.total_tokens), ((), 0))

    def test_prefers_referenced_import_and_keeps_it_after_symbol_cropping(self):
        dependency = "    import json as encoder\n"
        changed = "    return encoder.dumps({})\n"
        self.write(
            "module.py", "import pathlib\ndef render():\n" + dependency
            + "    # " + "x" * 100 + "\n" + changed,
        )
        builder, group = self.context({"module.py": (5,)})
        budget = estimate_tokens(changed) + estimate_tokens(dependency)

        bundle = builder.build(group, token_budget=budget)
        self.assertEqual([item.content for item in bundle.items], [changed, dependency])
        self.assertEqual(bundle.total_tokens, budget)

    def test_preserves_multiline_decorator_and_does_not_repeat_enclosed_method(self):
        source = "class C:\n    flag = True\n    @(\n        wrap\n    )\n    def run(self):\n        return 1\n"
        self.write("module.py", source)
        builder, group = self.context({"module.py": (3, 7)})
        method = source[source.index("    @("):]
        bundle = builder.build(group, token_budget=240)
        self.assertEqual([(item.start_line, item.content) for item in bundle.items], [(3, method)])

        builder, group = self.context({"module.py": (2, 7)})
        bundle = builder.build(group, token_budget=240)
        self.assertEqual([item.content for item in bundle.items], [source])

    def test_diff_line_numbers_survive_unicode_separator_in_python_string(self):
        first = "value = 'a\u2028b'"
        second = "next_value = 2"
        self.write("module.py", f"{first}\n{second}\n")
        diff = "\r\n".join(("--- /dev/null", "+++ b/module.py", "@@ -0,0 +1,2 @@",
                            "+" + first, "+" + second, ""))
        change = ChangeSet.from_diff(diff, "a" * 40, "b" * 40)
        group = ReviewGroup.from_paths(change, ("module.py",), "test")

        bundle = ContextBuilder(self.root, change).build(group, token_budget=240)
        self.assertEqual([(item.start_line, item.content) for item in bundle.items],
                         [(1, first + "\n"), (2, second + "\n")])

    def test_extracts_javascript_typescript_and_go_symbols_and_imports(self):
        js_import = 'import {format} from "./format.js";\n'
        js_symbol = '  function inner() {\n    return format(`值 = }`);\n  }\n'
        ts_import = 'import type { Item } from "./item";\n'
        ts_symbol = "export const run = <T extends Item>(item: T): T => {\n  return item;\n};\n"
        go_import = 'import (\n    f "fmt"\n)\n'
        go_symbol = 'func (c Counter) Label() string {\n    return f.Sprint("值")\n}\n'
        cases = [
            ("nested.js", js_import + "function outer() {\n" + js_symbol + "}\n",
             4, (3, 5, js_symbol), (1, 1, js_import)),
            ("generic.ts", ts_import + "\n" + ts_symbol,
             4, (3, 5, ts_symbol), (1, 1, ts_import)),
            ("counter.go", "package demo\n\n" + go_import + "\n" + go_symbol,
             8, (7, 9, go_symbol), (3, 5, go_import)),
        ]
        for path, source, line, symbol, dependency in cases:
            with self.subTest(path=path):
                self.write(path, source)
                builder, group = self.context({path: (line,)})
                bundle = builder.build(group, token_budget=240)
                self.assertEqual(
                    [(item.start_line, item.end_line, item.content) for item in bundle.items],
                    [symbol, dependency],
                )
                self.assertEqual([item.reason for item in bundle.items], ["changed-symbol", "module-import"])
                self.assertEqual([item.tool for item in bundle.items], ["tree-sitter", "tree-sitter"])
                self.assertTrue(all(item.path == path for item in bundle.items))

    def test_tsx_uses_its_own_grammar(self):
        source = "export function View() {\n  return <span>界面</span>;\n}\n"
        self.write("view.tsx", source)
        builder, group = self.context({"view.tsx": (2,)})

        bundle = builder.build(group, token_budget=240)
        self.assertEqual([(item.content, item.tool) for item in bundle.items], [(source, "tree-sitter")])

    def test_extracts_anonymous_default_exports(self):
        for signature in ("export default () => {", "export default function () {"):
            with self.subTest(signature=signature):
                source = signature + "\n  return 1;\n}\n"
                self.write("default.js", source)
                builder, group = self.context({"default.js": (2,)})

                bundle = builder.build(group, token_budget=240)
                self.assertEqual([(item.content, item.tool) for item in bundle.items], [(source, "tree-sitter")])

    def test_keeps_typescript_method_decorators_and_import_aliases(self):
        import_line = "import Item = Models.Item;\n"
        method = '  @route("/items")\n  // List items.\n  list(value: Item) {\n    return value;\n  }\n'
        self.write("handler.ts", import_line + "class Handler {\n" + method + "}\n")
        builder, group = self.context({"handler.ts": (3, 6)})

        bundle = builder.build(group, token_budget=240)
        self.assertEqual(
            [(item.start_line, item.end_line, item.content) for item in bundle.items],
            [(3, 7, method), (1, 1, import_line)],
        )

    def test_extracts_typescript_declaration_file_signatures(self):
        source = "export declare function run(\n  value: string,\n): void;\n"
        self.write("types.d.ts", source)
        builder, group = self.context({"types.d.ts": (2,)})

        bundle = builder.build(group, token_budget=240)
        self.assertEqual([(item.content, item.tool) for item in bundle.items], [(source, "tree-sitter")])

    def test_bad_syntax_and_unknown_extensions_use_only_changed_text(self):
        cases = [
            ("broken.js", 'import "./valid.js";\n', "export function broken( {\n"),
            ("broken.ts", 'import type { T } from "./type";\n', "interface Broken { value: =\n"),
            ("broken.go", 'package demo\nimport "fmt"\n', "func broken( {\n"),
            ("notes.txt", "before\n", "变更内容\n"),
        ]
        for path, prefix, changed_line in cases:
            with self.subTest(path=path):
                (self.root / path).write_bytes((prefix + changed_line).replace("\n", "\r\n").encode("utf-8"))
                line = prefix.count("\n") + 1
                diff = f"--- a/{path}\r\n+++ b/{path}\r\n@@ -{line - 1},0 +{line} @@\r\n+{changed_line}"
                change = ChangeSet.from_diff(diff, "a" * 40, "b" * 40)
                group = ReviewGroup.from_paths(change, (path,), "test")
                builder = ContextBuilder(self.root, change)

                bundle = builder.build(group, token_budget=240)
                self.assertEqual(
                    [(item.start_line, item.end_line, item.content, item.reason, item.tool) for item in bundle.items],
                    [(line, line, changed_line, "changed-line", "source-line")],
                )
                self.assertEqual(builder.build(group, token_budget=240), bundle)
                budget = estimate_tokens(changed_line)
                self.assertEqual(bundle.total_tokens, budget)
                self.assertEqual(builder.build(group, token_budget=budget - 1).items, ())

    def test_mixed_language_group_deduplicates_and_respects_its_budget(self):
        source = "function run() {\n  return '结果';\n}\n"
        for path in ("a.js", "b.ts"):
            self.write(path, source)
        budget = estimate_tokens(source)
        builder, group = self.context({"b.ts": (2,), "a.js": (2,)}, group_budget=budget * 2)

        bundle = builder.build(group, token_budget=240)
        self.assertEqual(bundle.token_budget, budget * 2)
        self.assertEqual(bundle.total_tokens, budget)
        self.assertEqual([(item.path, item.content) for item in bundle.items], [("a.js", source)])
        self.assertEqual(bundle.items[0].content_hash, hashlib.sha256(source.encode("utf-8")).hexdigest())
        self.assertLessEqual(builder.build(group, token_budget=budget - 1).total_tokens, budget - 1)

    def test_zero_budget_and_unavailable_or_binary_paths(self):
        self.write("deleted.py", "something = 1\n")
        (self.root / "data.bin").write_bytes(b"binary\x00payload\n")
        (self.root / "bad-encoding.ts").write_bytes(b"\xff\n")
        self.write("invalid.py", "def missing(\n")
        self.write("../outside.py", "value = 1\n")
        builder, group = self.context({
            "deleted.py": (), "data.bin": (1,), "bad-encoding.ts": (1,), "invalid.py": (1,), "missing.py": (1,),
            "../outside.py": (1,),
        })

        self.assertEqual(builder.build(group, token_budget=0).items, ())
        bundle = builder.build(group, token_budget=240)
        self.assertEqual([(item.path, item.content) for item in bundle.items],
                         [("invalid.py", "def missing(\n")])
        with self.assertRaises(ValueError):
            builder.build(group, token_budget=-1)

    def test_rejects_group_from_another_change_set(self):
        builder, group = self.context({"module.py": (1,)})
        another_change = ChangeSet("a" * 40, "c" * 40, (ChangedFile("module.py", (1,)),))
        other_group = ReviewGroup.from_paths(another_change, group.paths, "test")
        with self.assertRaises(ValueError):
            builder.build(other_group, token_budget=240)
