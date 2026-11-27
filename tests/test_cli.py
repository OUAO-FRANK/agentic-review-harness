import importlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path


RISKY_DIFF = """--- a/app.py
+++ b/app.py
@@ -0,0 +1 @@
+eval(user_input)
"""


class CliTests(unittest.TestCase):
    def _cli(self):
        self.assertIsNotNone(
            importlib.util.find_spec("evoagent.cli"),
            "evoagent.cli is missing",
        )
        return importlib.import_module("evoagent.cli")

    def _run_cli(self, argv, **kwargs):
        try:
            return self._cli().main(argv, **kwargs)
        except (SystemExit, TypeError) as exc:
            self.fail("CLI contract is unavailable: %s" % exc)

    def test_doctor_returns_zero_for_local_provider(self):
        output = io.StringIO()
        code = self._cli().main(
            ["doctor"],
            environ={"EVOAGENT_LLM_PROVIDER": "local"},
            stdout=output,
        )
        self.assertEqual(0, code)
        self.assertIn("provider: local", output.getvalue())

    def test_doctor_rejects_incomplete_custom_provider(self):
        error = io.StringIO()
        code = self._cli().main(
            ["doctor"],
            environ={"EVOAGENT_LLM_PROVIDER": "custom"},
            stderr=error,
        )
        self.assertEqual(1, code)
        self.assertIn("Custom LLM requires", error.getvalue())

    def test_doctor_restores_the_process_environment(self):
        before = dict(os.environ)
        self._cli().main(
            ["doctor"],
            environ={"EVOAGENT_LLM_PROVIDER": "local"},
            stdout=io.StringIO(),
        )
        self.assertEqual(before, dict(os.environ))

    def test_doctor_github_reports_missing_configuration(self):
        output = io.StringIO()
        code = self._run_cli(
            ["doctor", "--github"],
            environ={"EVOAGENT_LLM_PROVIDER": "local"},
            stdout=output,
        )
        self.assertEqual(1, code)
        self.assertIn("github: not configured", output.getvalue())
        self.assertIn("action: local diff ready", output.getvalue())

    def test_doctor_github_reports_missing_app_fields_without_secrets(self):
        output = io.StringIO()
        code = self._run_cli(
            ["doctor", "--github"],
            environ={
                "EVOAGENT_LLM_PROVIDER": "local",
                "EVOAGENT_GITHUB_APP_ID": "123",
                "EVOAGENT_GITHUB_WEBHOOK_SECRET": "private-webhook-secret",
            },
            stdout=output,
        )
        self.assertEqual(1, code)
        self.assertIn("github: app incomplete", output.getvalue())
        self.assertIn("EVOAGENT_GITHUB_APP_SLUG", output.getvalue())
        self.assertIn("EVOAGENT_GITHUB_PRIVATE_KEY_PATH", output.getvalue())
        self.assertNotIn("private-webhook-secret", output.getvalue())

    def test_doctor_github_accepts_complete_app_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "app.pem"
            key_path.write_text("test key", encoding="utf-8")
            output = io.StringIO()
            code = self._run_cli(
                ["doctor", "--github"],
                environ={
                    "EVOAGENT_LLM_PROVIDER": "local",
                    "EVOAGENT_GITHUB_APP_ID": "123",
                    "EVOAGENT_GITHUB_APP_SLUG": "review-app",
                    "EVOAGENT_GITHUB_PRIVATE_KEY_PATH": str(key_path),
                    "EVOAGENT_GITHUB_WEBHOOK_SECRET": "secret",
                    "EVOAGENT_PUBLIC_BASE_URL": "https://example.com",
                },
                stdout=output,
            )
        self.assertEqual(0, code)
        self.assertIn("github: app ready", output.getvalue())

    def test_doctor_github_accepts_pat_configuration(self):
        output = io.StringIO()
        code = self._run_cli(
            ["doctor", "--github"],
            environ={
                "EVOAGENT_LLM_PROVIDER": "local",
                "EVOAGENT_GITHUB_TOKEN": "private-token",
                "EVOAGENT_GITHUB_WEBHOOK_SECRET": "secret",
            },
            stdout=output,
        )
        self.assertEqual(0, code)
        self.assertIn("github: pat ready", output.getvalue())
        self.assertNotIn("private-token", output.getvalue())

    def test_doctor_github_rejects_missing_key_file_and_http_app_url(self):
        output = io.StringIO()
        code = self._run_cli(
            ["doctor", "--github"],
            environ={
                "EVOAGENT_LLM_PROVIDER": "local",
                "EVOAGENT_GITHUB_APP_ID": "123",
                "EVOAGENT_GITHUB_APP_SLUG": "review-app",
                "EVOAGENT_GITHUB_PRIVATE_KEY_PATH": "missing-app.pem",
                "EVOAGENT_GITHUB_WEBHOOK_SECRET": "secret",
                "EVOAGENT_PUBLIC_BASE_URL": "http://example.com",
            },
            stdout=output,
        )
        self.assertEqual(1, code)
        self.assertIn("EVOAGENT_GITHUB_PRIVATE_KEY_PATH (file not found)", output.getvalue())
        self.assertIn("EVOAGENT_PUBLIC_BASE_URL (https required)", output.getvalue())

    def test_review_reads_a_diff_from_stdin(self):
        output = io.StringIO()
        code = self._run_cli(
            ["review"],
            stdin=io.StringIO(RISKY_DIFF),
            stdout=output,
        )
        self.assertEqual(0, code)
        self.assertIn("SEC-EVAL", output.getvalue())
        self.assertIn("app.py:1", output.getvalue())

    def test_review_reads_a_utf8_diff_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "change.diff"
            path.write_text(RISKY_DIFF, encoding="utf-8")
            output = io.StringIO()
            code = self._run_cli(["review", str(path)], stdout=output)
        self.assertEqual(0, code)
        self.assertIn("1 finding", output.getvalue())

    def test_review_rejects_input_without_added_lines(self):
        error = io.StringIO()
        code = self._run_cli(
            ["review"],
            stdin=io.StringIO("not a unified diff"),
            stderr=error,
        )
        self.assertEqual(1, code)
        self.assertIn("reviewable added lines", error.getvalue())

    def test_review_emits_stable_json_output(self):
        first = io.StringIO()
        second = io.StringIO()
        first_code = self._run_cli(
            ["review", "--format", "json"],
            stdin=io.StringIO(RISKY_DIFF),
            stdout=first,
        )
        second_code = self._run_cli(
            ["review", "--format", "json"],
            stdin=io.StringIO(RISKY_DIFF),
            stdout=second,
        )

        self.assertEqual(0, first_code)
        self.assertEqual(0, second_code)
        self.assertEqual(first.getvalue(), second.getvalue())
        payload = json.loads(first.getvalue())
        self.assertEqual(
            {
                "files",
                "findings",
                "reviewer",
                "schema_version",
                "status",
                "summary",
            },
            set(payload),
        )
        self.assertEqual(1, payload["schema_version"])
        self.assertEqual("ok", payload["status"])
        self.assertEqual("local-rules", payload["reviewer"])
        self.assertEqual({"file_count": 1, "finding_count": 1}, payload["summary"])
        self.assertEqual(["app.py"], payload["files"])
        self.assertEqual("SEC-EVAL", payload["findings"][0]["rule_id"])
        self.assertEqual("critical", payload["findings"][0]["severity"])

    def test_review_emits_structured_json_errors(self):
        output = io.StringIO()
        error = io.StringIO()
        code = self._run_cli(
            ["review", "--format", "json"],
            stdin=io.StringIO("not a unified diff"),
            stdout=output,
            stderr=error,
        )

        self.assertEqual(1, code)
        self.assertEqual("", error.getvalue())
        self.assertEqual(
            {
                "schema_version": 1,
                "status": "error",
                "error": {
                    "code": "invalid-diff",
                    "message": "input contains no reviewable added lines",
                },
            },
            json.loads(output.getvalue()),
        )

    def test_review_reports_json_file_read_errors(self):
        output = io.StringIO()
        error = io.StringIO()
        code = self._run_cli(
            ["review", "missing.diff", "--format", "json"],
            stdout=output,
            stderr=error,
        )

        self.assertEqual(1, code)
        self.assertEqual("", error.getvalue())
        payload = json.loads(output.getvalue())
        self.assertEqual("error", payload["status"])
        self.assertEqual("input-read-failed", payload["error"]["code"])
        self.assertIn("missing.diff", payload["error"]["message"])

    def test_plan_matches_runtime_group_ids_and_reports_filtered_paths(self):
        from evoagent.review import ChangePlanner, ChangeSet

        diff = RISKY_DIFF + RISKY_DIFF.replace("app.py", "vendor/helper.py")
        base, head = "a" * 40, "b" * 40
        args = ["plan", "--base-sha", base, "--head-sha", head, "--max-tokens", "16"]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "change.diff"
            path.write_text(diff, encoding="utf-8-sig")
            reports = []
            for source in (["-"], [str(path)]):
                output = io.StringIO()
                code = self._run_cli(args + source, stdin=io.StringIO(diff), stdout=output)
                self.assertEqual(0, code)
                reports.append(json.loads(output.getvalue()))
        self.assertEqual(*reports)
        report = reports[0]
        expected, = ChangePlanner(max_tokens=16).plan(ChangeSet.from_diff(diff, base, head))
        group, = report["groups"]
        self.assertEqual(expected.group_id, group["group_id"])
        self.assertEqual(["app.py"], group["paths"])
        self.assertEqual("oversized-file", group["reason"])
        self.assertEqual(16, group["token_budget"])
        self.assertGreater(group["estimated_tokens"], group["token_budget"])
        self.assertEqual(["vendor/helper.py"], report["excluded_paths"])
        self.assertEqual((base, head), (report["base_sha"], report["head_sha"]))

    def test_plan_rejects_malformed_input_with_json_error(self):
        args = ["plan", "--base-sha", "a" * 40, "--head-sha", "b" * 40]
        for diff in ("not a patch", RISKY_DIFF.removesuffix("+eval(user_input)\n")):
            with self.subTest(diff=diff):
                output = io.StringIO()
                self.assertEqual(1, self._run_cli(args, stdin=io.StringIO(diff), stdout=output))
                self.assertEqual("invalid-diff", json.loads(output.getvalue())["error"]["code"])

    def test_plan_reports_binary_patch_without_file_headers(self):
        boundary = "diff --git a/icon.png b/icon.png"
        diff = (boundary + "\nBinary files a/icon.png and b/icon.png differ\n"
                + "diff --git a/app.py b/app.py\n" + RISKY_DIFF)
        output = io.StringIO()
        code = self._run_cli(
            ["plan", "--base-sha", "a" * 40, "--head-sha", "b" * 40],
            stdin=io.StringIO(diff),
            stdout=output,
        )
        self.assertEqual(0, code)
        report = json.loads(output.getvalue())
        self.assertEqual([boundary], report["metadata_only"])
        self.assertEqual(["app.py"], report["groups"][0]["paths"])

    def test_plan_decodes_git_quoted_utf8_paths(self):
        # Git's default core.quotePath encodes each UTF-8 byte in octal.
        path = r"\346\265\213.py"
        diff = f'--- "a/{path}"\n+++ "b/{path}"\n@@ -0,0 +1 @@\n+value = 1\n'
        output = io.StringIO()
        code = self._run_cli(["plan", "--base-sha", "a" * 40, "--head-sha", "b" * 40],
                             stdin=io.StringIO(diff), stdout=output)
        self.assertEqual(0, code)
        self.assertEqual(["测.py"], json.loads(output.getvalue())["groups"][0]["paths"])

    def test_plan_rejects_malformed_hunk_header(self):
        output = io.StringIO()
        code = self._run_cli(["plan", "--base-sha", "a" * 40, "--head-sha", "b" * 40],
                             stdin=io.StringIO(RISKY_DIFF.replace("@@ -0,0 +1 @@", "@@ broken @@")),
                             stdout=output)
        self.assertEqual(1, code)
        self.assertEqual("invalid-diff", json.loads(output.getvalue())["error"]["code"])


if __name__ == "__main__":
    unittest.main()
