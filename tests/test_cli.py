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


if __name__ == "__main__":
    unittest.main()
