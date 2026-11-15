import importlib
import importlib.util
import io
import os
import unittest


class CliTests(unittest.TestCase):
    def _cli(self):
        self.assertIsNotNone(
            importlib.util.find_spec("evoagent.cli"),
            "evoagent.cli is missing",
        )
        return importlib.import_module("evoagent.cli")

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


if __name__ == "__main__":
    unittest.main()
