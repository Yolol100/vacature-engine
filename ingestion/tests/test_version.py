from __future__ import annotations

import json
import tomllib
import unittest
from pathlib import Path

import vacature_ingestion


class VersionTests(unittest.TestCase):
    def test_runtime_version_matches_project_metadata(self):
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        self.assertEqual(vacature_ingestion.__version__, metadata["project"]["version"])

    def test_release_manifest_matches_project_metadata(self):
        root = Path(__file__).resolve().parents[1]
        metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        manifest = json.loads((root / "RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], metadata["project"]["version"])
        self.assertEqual(manifest["version"], vacature_ingestion.__version__)
        self.assertEqual(manifest["runtime_dependencies"], metadata["project"].get("dependencies", []))


if __name__ == "__main__":
    unittest.main()
