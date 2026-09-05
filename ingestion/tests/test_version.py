from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

import vacature_ingestion


class VersionTests(unittest.TestCase):
    def test_runtime_version_matches_project_metadata(self):
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        self.assertEqual(vacature_ingestion.__version__, metadata["project"]["version"])


if __name__ == "__main__":
    unittest.main()
