import unittest
from dataclasses import FrozenInstanceError

from evoagent.review.planner import ChangePlanner
from evoagent.review.types import ChangeSet, ReviewGroup


BASE = "a" * 40
HEAD = "b" * 40
DIFF = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1,2 @@
 existing
+new_line = 1
diff --git a/vendor/tool.py b/vendor/tool.py
--- a/vendor/tool.py
+++ b/vendor/tool.py
@@ -0,0 +1 @@
+ignored = True
diff --git a/src/package-lock.json b/src/package-lock.json
--- a/src/package-lock.json
+++ b/src/package-lock.json
@@ -0,0 +1 @@
+{}
diff --git a/src/generated.py b/src/generated.py
--- a/src/generated.py
+++ b/src/generated.py
@@ -0,0 +1 @@
+built = True
diff --git a/assets/logo.png b/assets/logo.png
--- a/assets/logo.png
+++ b/assets/logo.png
@@ -0,0 +1 @@
+binary
diff --git a/tests/test_app.py b/tests/test_app.py
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -0,0 +1 @@
+assert True
"""


class ReviewPlannerTests(unittest.TestCase):
    def test_change_set_is_immutable_and_records_added_lines(self):
        change = ChangeSet.from_diff(DIFF, BASE, HEAD)
        self.assertEqual(BASE, change.base_sha)
        self.assertEqual(HEAD, change.head_sha)
        self.assertEqual(6, len(change.files))
        self.assertEqual((2,), change.file("src/app.py").added_lines)
        with self.assertRaises(FrozenInstanceError):
            change.head_sha = BASE

    def test_change_set_includes_deleted_file_without_added_lines(self):
        diff = "diff --git a/src/old.py b/src/old.py\n--- a/src/old.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-old = 1\n"
        change = ChangeSet.from_diff(diff, BASE, HEAD)
        self.assertEqual((), change.file("src/old.py").added_lines)

    def test_change_set_rejects_invalid_shas_and_duplicate_paths(self):
        with self.assertRaises(ValueError):
            ChangeSet.from_diff(DIFF, "invalid", HEAD)
        with self.assertRaises(ValueError):
            ChangeSet.from_diff(DIFF + DIFF, BASE, HEAD)

    def test_filter_excludes_nonreviewable_paths_by_component(self):
        paths = tuple(item.path for item in ChangePlanner().reviewable_files(
            ChangeSet.from_diff(DIFF, BASE, HEAD)
        ))
        self.assertEqual(("src/app.py", "tests/test_app.py"), paths)
        self.assertTrue(ChangePlanner().is_reviewable("src/vendor_api.py"))
        self.assertTrue(ChangePlanner().is_reviewable("src/generated_client.py"))

    def test_review_group_identity_is_stable_and_validated(self):
        change = ChangeSet.from_diff(DIFF, BASE, HEAD)
        first = ReviewGroup.from_paths(change, ["tests/test_app.py", "src/app.py"], "module")
        second = ReviewGroup.from_paths(change, ["src/app.py", "tests/test_app.py"], "module")
        self.assertEqual(first.group_id, second.group_id)
        self.assertEqual(("src/app.py", "tests/test_app.py"), first.paths)
        self.assertEqual(HEAD, first.head_sha)
        with self.assertRaises(ValueError):
            ReviewGroup.from_paths(change, ["src/unknown.py"], "module")
        with self.assertRaises(ValueError):
            ReviewGroup.from_paths(change, ["src/app.py", "src/app.py"], "module")


if __name__ == "__main__":
    unittest.main()
