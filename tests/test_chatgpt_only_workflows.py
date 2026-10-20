from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ChatGPTOnlyWorkflowTests(unittest.TestCase):
    def test_github_actions_are_ci_only(self):
        workflows = ROOT / ".github" / "workflows"
        self.assertEqual(["ingestion-tests.yml"], sorted(p.name for p in workflows.glob("*.yml")))
        workflow = (workflows / "ingestion-tests.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", workflow)
        self.assertIn("python -m unittest discover", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("scripts/one_pass_vacancies.py", workflow)

    def test_register_is_policy_owner_and_static_specs_are_not_registry(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Vacature Register", readme)
        self.assertIn("source-specs.deploy.json", readme)
        self.assertIn("source-specs.google-optional.json", readme)
        self.assertIn("GitHub Actions are CI-only", readme)

if __name__ == "__main__":
    unittest.main()
