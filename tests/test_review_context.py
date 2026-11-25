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

    def test_zero_budget_and_non_python_or_unavailable_paths(self):
        self.write("deleted.py", "something = 1\n")
        self.write("module.js", "export function run() {}\n")
        self.write("invalid.py", "def missing(\n")
        self.write("../outside.py", "value = 1\n")
        builder, group = self.context({
            "deleted.py": (), "module.js": (1,), "invalid.py": (1,), "missing.py": (1,),
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
