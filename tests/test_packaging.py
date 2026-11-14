import subprocess
import sys
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_project_builds_an_installable_wheel(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            build_root = Path(temp_dir) / "project"
            build_root.mkdir()
            for filename in ("pyproject.toml", "requirements.txt", "README.md"):
                shutil.copy2(ROOT / filename, build_root / filename)
            shutil.copytree(
                ROOT / "evoagent",
                build_root / "evoagent",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            wheel_dir = Path(temp_dir) / "wheelhouse"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--no-build-isolation",
                    "--wheel-dir",
                    wheel_dir,
                    str(build_root),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            wheels = list(wheel_dir.glob("agentic_review_harness-*.whl"))
            self.assertEqual(1, len(wheels))
            with zipfile.ZipFile(wheels[0]) as archive:
                self.assertIn("evoagent/__init__.py", archive.namelist())


if __name__ == "__main__":
    unittest.main()
