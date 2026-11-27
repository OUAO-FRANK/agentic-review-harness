import unittest

from evoagent import diff_parser
from evoagent.context_manager import ContextManager
from evoagent.diff_parser import parse_unified_diff
from evoagent.review.pipeline import _file_patches
from evoagent.review.types import ChangeSet


DIFF = """diff --git a/app.py b/app.py
index 123..456 100644
--- a/app.py
+++ b/app.py
@@ -2,3 +2,4 @@ def run():
 keep = True
-old = 1
+new = 2
+eval(user_input)
 tail = 3
"""


class DiffParserTests(unittest.TestCase):
    def test_quoted_path_matches_source_context_and_scoped_patch(self):
        encoded = r"\346\265\213\tfile.py"
        path = "测\tfile.py"
        diff = (f'--- "a/{encoded}"\told timestamp\n'
                f'+++ "b/{encoded}"\tnew timestamp\n@@ -0,0 +1 @@\n+value = 1\n')
        self.assertEqual([path], parse_unified_diff(diff).files)
        self.assertEqual((1,), ChangeSet.from_diff(diff, "a" * 40, "b" * 40).file(path).added_lines)
        self.assertEqual(path, ContextManager().compress_diff(diff)["selected_hunks"][0]["path"])
        self.assertEqual({path: diff}, _file_patches(diff))

    def test_non_strict_parser_tolerates_unrecognized_hunk_header(self):
        diff = "--- a/demo.py\n+++ b/demo.py\n@@ broken @@\n"
        self.assertEqual(["demo.py"], parse_unified_diff(diff).files)
        with self.assertRaisesRegex(ValueError, "malformed unified diff hunk"):
            list(diff_parser.iter_diff_lines(diff, strict=True))

    def test_parses_added_line_numbers(self):
        parsed = parse_unified_diff(DIFF)
        self.assertEqual(["app.py"], parsed.files)
        self.assertEqual([(3, "new = 2"), (4, "eval(user_input)")], [(x.line, x.content) for x in parsed.added_lines])

    def test_header_like_source_keeps_its_file_and_added_line_numbers(self):
        diff = (
            "--- a/doc.md\n+++ b/doc.md\n@@ -10,2 +10,3 @@\n"
            "--- removed\n+++ b/doc.md\n+after\n tail\n"
        )
        parsed = parse_unified_diff(diff)
        self.assertEqual(["doc.md"], parsed.files)
        self.assertEqual(
            [("doc.md", 10, "++ b/doc.md"), ("doc.md", 11, "after")],
            [(line.path, line.line, line.content) for line in parsed.added_lines],
        )
        change = ChangeSet.from_diff(diff, "a" * 40, "b" * 40)
        self.assertEqual((10, 11), change.file("doc.md").added_lines)
        hunks = ContextManager().compress_diff(diff)["selected_hunks"]
        self.assertEqual(1, len(hunks))
        self.assertEqual("doc.md", hunks[0]["path"])
        self.assertIn("--- removed\n+++ b/doc.md\n+after", hunks[0]["content"])

    def test_strict_hunks_reject_a_boundary_or_end_before_the_counts_are_met(self):
        previous = "--- a/a.py\n+++ b/a.py\n@@ -1 +1,2 @@\n-before\n+after\n"
        for diff in (previous, previous + DIFF):
            with self.subTest(diff=diff):
                with self.assertRaisesRegex(ValueError, "hunk"):
                    list(diff_parser.iter_diff_lines(diff, strict=True))

    def test_strict_hunks_keep_no_newline_markers_and_reject_overlong_body(self):
        diff = "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-before\n+after\n\\ No newline at end of file\n"
        self.assertEqual(
            ("body", "\\ No newline at end of file"),
            list(diff_parser.iter_diff_lines(diff, strict=True))[-1],
        )
        with self.assertRaisesRegex(ValueError, "hunk"):
            list(diff_parser.iter_diff_lines(diff + "+too many lines\n", strict=True))


if __name__ == "__main__":
    unittest.main()

