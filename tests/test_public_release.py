import unittest
from pathlib import Path

from evoagent.config import Settings


ROOT = Path(__file__).resolve().parents[1]


class PublicReleaseTests(unittest.TestCase):
    def test_public_brand_and_compatibility_defaults(self):
        settings = Settings.from_env()
        self.assertEqual("Agentic Review Harness", settings.openrouter_app_name)
        self.assertEqual("agentic-review-harness", settings.otel_service_name)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Python 包名 `evoagent`", readme)
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


if __name__ == "__main__":
    unittest.main()
