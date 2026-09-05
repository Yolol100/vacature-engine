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
    def test_deploy_is_exact_live_plus_daily_union(self):
        live = _load("source-specs.live.json")
        daily = _load("source-specs.daily.json")
        deploy = _load("source-specs.deploy.json")
        self.assertEqual(deploy, live + daily)

    def test_source_instances_are_unique_per_lane(self):
        for filename in ("source-specs.live.json", "source-specs.daily.json", "source-specs.deploy.json"):
            specs = _load(filename)
            instances = [_instance_id(spec) for spec in specs]
            self.assertEqual(len(instances), len(set(instances)), filename)


if __name__ == "__main__":
    unittest.main()
