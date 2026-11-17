import unittest
from pathlib import Path

import yaml

from evoagent.config import Settings


ROOT = Path(__file__).resolve().parents[1]


class PublicReleaseTests(unittest.TestCase):
    def test_public_brand_and_compatibility_defaults(self):
        settings = Settings.from_env()
        self.assertEqual("Agentic Review Harness", settings.openrouter_app_name)
        self.assertEqual("agentic-review-harness", settings.otel_service_name)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Python 包名 `evoagent`", readme)
        self.assertIn("合成 fixture", readme)
        self.assertIn("不代表真实生产 PR", readme)
        self.assertIn("EVOAGENT_*", readme)
        self.assertNotIn("python -m Agentic Review Harness", readme)

    def test_compose_requires_explicit_credentials(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("AGENTIC_REVIEW_POSTGRES_PASSWORD:?", compose)
        self.assertIn("EVOAGENT_AUTH_SECRET:?", compose)
        self.assertIn("EVOAGENT_BOOTSTRAP_ADMIN_PASSWORD:?", compose)
        self.assertIn('127.0.0.1:8080:8080', compose)
        self.assertNotIn("local-only-change-this-secret", compose)
        self.assertNotIn("evoagent-local-admin", compose)

    def test_ci_runs_the_baseline_on_windows_and_linux(self):
        workflow_path = ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(workflow_path.is_file(), "cross-platform CI workflow is missing")
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertIn("ubuntu-latest", workflow)
        self.assertIn("windows-latest", workflow)
        self.assertIn('python-version: "3.11"', workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("python -m compileall -q evoagent scripts tests", workflow)

    def test_github_action_declares_inputs_outputs_and_permissions(self):
        action_path = ROOT / "action.yml"
        self.assertTrue(action_path.is_file(), "GitHub Action metadata is missing")
        action = yaml.safe_load(action_path.read_text(encoding="utf-8"))

        self.assertEqual("composite", action["runs"]["using"])
        self.assertEqual(
            {"diff-path", "mode", "output-path", "python-version"},
            set(action["inputs"]),
        )
        self.assertEqual("fast", action["inputs"]["mode"]["default"])
        self.assertEqual("3.11", action["inputs"]["python-version"]["default"])
        self.assertEqual(
            "agentic-review.json", action["inputs"]["output-path"]["default"]
        )
        self.assertEqual(
            "${{ inputs.output-path }}",
            action["outputs"]["report-path"]["value"],
        )

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("contents: read", readme)
        self.assertIn("pull-requests: write", readme)
        self.assertNotIn("token", action["inputs"])

    def test_github_action_runs_the_cli_and_uploads_the_report(self):
        action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
        steps = action["runs"]["steps"]

        setup_steps = [
            step for step in steps if step.get("uses") == "actions/setup-python@v7"
        ]
        self.assertEqual(1, len(setup_steps), "Python setup step is missing")
        setup = setup_steps[0]
        self.assertEqual("${{ inputs.python-version }}", setup["with"]["python-version"])

        commands = "\n".join(step.get("run", "") for step in steps)
        self.assertIn('python -m pip install "$GITHUB_ACTION_PATH"', commands)
        self.assertIn(
            'agentic-review review "$DIFF_PATH" --format json > "$OUTPUT_PATH"',
            commands,
        )

        review_steps = [step for step in steps if step.get("name") == "Run review"]
        self.assertEqual(1, len(review_steps), "review execution step is missing")
        review = review_steps[0]
        self.assertEqual("${{ inputs.diff-path }}", review["env"]["DIFF_PATH"])
        self.assertEqual("${{ inputs.output-path }}", review["env"]["OUTPUT_PATH"])

        upload_steps = [
            step for step in steps if step.get("uses") == "actions/upload-artifact@v7"
        ]
        self.assertEqual(1, len(upload_steps), "artifact upload step is missing")
        upload = upload_steps[0]
        self.assertEqual("${{ inputs.output-path }}", upload["with"]["path"])
        self.assertEqual("error", upload["with"]["if-no-files-found"])

    def test_github_action_rejects_unavailable_deep_mode(self):
        action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
        validation = action["runs"]["steps"][0]["run"]
        self.assertNotIn("fast|deep", validation)
        self.assertIn("deep mode is not available", validation)

    def test_readme_recommends_github_app_with_installation_credentials(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        github_section = readme.split("## GitHub Webhook", 1)[1].split("## 接入方式", 1)[0]
        self.assertIn("推荐使用 GitHub App", github_section)
        self.assertIn("EVOAGENT_GITHUB_APP_ID", github_section)
        self.assertIn("EVOAGENT_GITHUB_APP_SLUG", github_section)
        self.assertIn("EVOAGENT_GITHUB_PRIVATE_KEY_PATH", github_section)
        self.assertIn("/github/install", github_section)
        self.assertIn("/github/setup", github_section)
        self.assertIn("Pull requests: Read", github_section)
        self.assertIn("Contents: Read", github_section)
        self.assertIn("fine-grained PAT", github_section)


if __name__ == "__main__":
    unittest.main()
