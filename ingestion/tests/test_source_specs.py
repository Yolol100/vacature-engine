from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _load(name: str) -> list[dict[str, object]]:
    value = json.loads((ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise AssertionError(f"{name} must contain a JSON array")
    return value

class SourceSpecTests(unittest.TestCase):
    def test_only_two_technical_source_configurations_remain(self):
        files = sorted(p.name for p in ROOT.glob("source-specs.*.json"))
        self.assertEqual(["source-specs.deploy.json", "source-specs.google-optional.json"], files)

    def test_deploy_source_instances_are_unique(self):
        specs = _load("source-specs.deploy.json")
        keys = [(spec.get("source_id"), spec.get("account")) for spec in specs]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertGreaterEqual(len(specs), 20)
        self.assertTrue(all("status" not in spec for spec in specs))

    def test_core_free_feeds_remain_in_deploy(self):
        specs = _load("source-specs.deploy.json")
        ids = {str(spec.get("source_id")) for spec in specs}
        self.assertTrue({"we-work-remotely", "remote-ok", "himalayas", "jobicy-api", "remotive"}.issubset(ids))

    def test_wordpress_and_automation_employer_adapters_remain(self):
        specs = _load("source-specs.deploy.json")
        n8n = [spec for spec in specs if spec.get("source_id") == "ashby" and spec.get("account") == "n8n"]
        human_made = [spec for spec in specs if spec.get("employer") == "Human Made"]
        self.assertEqual(1, len(n8n))
        self.assertEqual("company-n8n", n8n[0].get("options", {}).get("registry_source_id"))
        self.assertEqual(1, len(human_made))
        self.assertEqual("workable", human_made[0].get("adapter"))

    def test_google_requires_explicit_registered_source(self):
        google = _load("source-specs.google-optional.json")
        self.assertEqual(1, len(google))
        self.assertEqual("google-jobs", google[0].get("source_id"))

if __name__ == "__main__":
    unittest.main()
