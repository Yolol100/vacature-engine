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

    def test_searxng_after_checkout_has_only_localhost_access_and_no_volume_precheckout(self):
        root=Path(__file__).resolve().parents[1]
        workflow=(root/".github/workflows/vacature-public-browser-30m.yml").read_text(encoding="utf8")
        config=(root/"searxng/settings.yml").read_text(encoding="utf8")
        self.assertLess(workflow.index("Checkout trusted main source"),
                        workflow.index("Start private SearXNG after checkout"))
        self.assertLess(workflow.index("Start private SearXNG after checkout"),
                        workflow.index("Scan registered public sources"))
        self.assertNotIn("\nservices:",workflow)
        self.assertIn("docker run --detach",workflow)
        self.assertIn("--publish 127.0.0.1:8080:8080",workflow)
        self.assertIn("trusted-source/searxng/settings.yml",workflow)
        self.assertIn("target=/etc/searxng/settings.yml,readonly",workflow)
        self.assertIn("SEARXNG_ENABLED=true",workflow)
        self.assertIn("docker rm --force vacancy-radar-searxng",workflow)
        self.assertIn("use_default_settings: true",config)
        self.assertIn("    - json",config)
        self.assertNotIn("\nengines:",config)
        self.assertNotIn("curl_cffi",workflow)
        self.assertNotIn("proxy",workflow.lower())
        self.assertNotIn("secrets.SEARXNG",workflow)
        # Private candidates/applications remain managed by the Google Script.
        self.assertNotIn("CandidateEvidence",workflow)
        self.assertNotIn("submit_application",workflow)

    def test_register_is_policy_owner_and_static_specs_are_not_registry(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Vacature Register", readme)
        self.assertIn("source-specs.deploy.json", readme)
        self.assertIn("source-specs.google-optional.json", readme)
        self.assertIn("public-only", readme)

if __name__ == "__main__":
    unittest.main()
