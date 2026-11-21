from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ChatGPTOnlyWorkflowTests(unittest.TestCase):
    def test_authorized_worker_is_isolated_from_private_automations(self):
        workflows = ROOT / ".github" / "workflows"
        # Keep protected offline tests, safe code sync and the user-authorized
        # public-only 30-minute browser worker separate.
        self.assertEqual(
            ["ingestion-tests.yml", "vacature-public-browser-30m.yml",
             "vacature-radar-script-sync.yml"],
            sorted(p.name for p in workflows.glob("*.yml")),
        )
        workflow = (workflows / "ingestion-tests.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", workflow)
        self.assertIn("python -m unittest discover", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("scripts/one_pass_vacancies.py", workflow)

        sync = (workflows / "vacature-radar-script-sync.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", sync)
        self.assertIn("automation/google-apps-script/Code.gs", sync)
        self.assertIn("vars.VACATURE_RADAR_AUTO_DEPLOY == 'true'", sync)
        self.assertIn("RADAR_EXPECTED_LIVE_SHA256", sync)
        self.assertIn("RADAR_EXPECTED_GITHUB_SHA256", sync)
        self.assertIn("secrets.RADAR_SCRIPT_ID", sync)
        self.assertIn("schedule:", sync)
        self.assertIn("github.event_name == 'schedule'", sync)
        self.assertIn("RADAR_SYNC_MODE=inspect", sync)
        self.assertIn("Reject direct pushes for automatic Apps Script deployments", sync)
        self.assertIn("pull-requests: read", sync)
        self.assertNotIn("runVacatureRadar", sync)
        self.assertNotIn("scripts/one_pass_vacancies.py", sync)

        public = (workflows / "vacature-public-browser-30m.yml").read_text(encoding="utf-8")
        self.assertIn("7 * * * *", public)
        self.assertIn("37 * * * *", public)
        self.assertIn("workflow_dispatch:", public)
        self.assertIn("contents: write", public)
        self.assertIn("persist-credentials: false", public)
        self.assertIn("radar-public-data", public)
        self.assertIn("--max-render 90", public)
        self.assertIn("ingestion/sources.public-snapshot.json", public)
        self.assertIn("test_scheduled_worker.py", public)
        self.assertEqual(public.count("secrets."), 1)
        self.assertIn("secrets.SERPAPI_API_KEY", public)
        self.assertIn("google_check", public)
        self.assertNotIn("secrets.RADAR_GOOGLE_REFRESH_TOKEN", public)
        self.assertNotIn("RADAR_GOOGLE_REFRESH_TOKEN", public)
        self.assertNotIn("scripts/one_pass_vacancies.py", public)
        self.assertNotIn("CandidateEvidence", public)
        self.assertNotIn("submit_application", public)

    def test_register_is_policy_owner_and_static_specs_are_not_registry(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Vacature Register", readme)
        self.assertIn("source-specs.deploy.json", readme)
        self.assertIn("source-specs.google-optional.json", readme)
        self.assertIn("public-only", readme)

if __name__ == "__main__":
    unittest.main()
