from pathlib import Path
import re
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DependencyPolicyTests(unittest.TestCase):
    def test_runtime_dependencies_are_empty(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = data["project"].get("dependencies", [])
        self.assertEqual([], dependencies)

    def test_build_backend_requirement_is_exactly_pinned(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        requirements = data["build-system"]["requires"]
        self.assertEqual(1, len(requirements))
        self.assertRegex(requirements[0], re.compile(r"^[A-Za-z0-9_.-]+==[0-9][A-Za-z0-9_.+-]*$"))


if __name__ == "__main__":
    unittest.main()
