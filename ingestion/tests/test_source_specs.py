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


def _instance_id(spec: dict[str, object]) -> str:
    return f"{spec.get('source_id')}:{spec.get('account')}"


class SourceSpecTests(unittest.TestCase):
    def test_deploy_is_exact_live_plus_fast_plus_daily_union(self):
        live = _load("source-specs.live.json")
        fast = _load("source-specs.fast.json")
        daily = _load("source-specs.daily.json")
        deploy = _load("source-specs.deploy.json")
        self.assertEqual(deploy, live + fast + daily)

    def test_source_instances_are_unique_per_lane(self):
        for filename in (
            "source-specs.live.json",
            "source-specs.fast.json",
            "source-specs.daily.json",
            "source-specs.radar.json",
            "source-specs.deploy.json",
        ):
            specs = _load(filename)
            instances = [_instance_id(spec) for spec in specs]
            self.assertEqual(len(instances), len(set(instances)), filename)

    def test_fast_lane_contains_only_registered_high_priority_feeds(self):
        fast = _load("source-specs.fast.json")
        self.assertEqual(
            ["we-work-remotely", "remote-ok"],
            [str(spec.get("source_id")) for spec in fast],
        )
        self.assertTrue(all(spec.get("listing_language") == "en" for spec in fast))

    def test_radar_lane_is_direct_registered_ats_only(self):
        radar = _load("source-specs.radar.json")
        self.assertGreaterEqual(len(radar), 10)
        self.assertTrue(all(spec.get("source_type") == "ats" for spec in radar))
        for spec in radar:
            options = spec.get("options")
            self.assertIsInstance(options, dict)
            self.assertTrue(str(options.get("registry_source_id") or "").startswith("company-"))

    def test_human_made_uses_public_workable_adapter_in_live_and_radar(self):
        for filename in ("source-specs.live.json", "source-specs.radar.json"):
            specs = _load(filename)
            matches = [spec for spec in specs if spec.get("employer") == "Human Made"]
            self.assertEqual(1, len(matches), filename)
            self.assertEqual("workable", matches[0].get("adapter"))
            self.assertEqual("humanmade", matches[0].get("account"))


if __name__ == "__main__":
    unittest.main()
