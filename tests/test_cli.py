import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = {
    "min_monthly_salary_eur": 3500,
    "max_posting_age_days": 120,
    "max_output_roles": 10,
    "min_output_score": 75,
    "min_core_fit": 40,
    "min_evidence_fit": 10,
}
VACANCY = {
    "title": "Senior WordPress Developer",
    "url": "https://example.com/job",
    "posted_date": "2026-08-20",
    "fully_remote": True,
    "geography_compatible": True,
    "wordpress_related": True,
    "central_hard_mismatch": False,
    "salary_monthly_eur": 4500,
    "core_fit": 40,
    "evidence_fit": 18,
    "workstyle_fit": 10,
}


class CliTests(unittest.TestCase):
    def run_cli(self, payload):
        return subprocess.run(
            [sys.executable, "-m", "vacature_engine"],
            cwd=ROOT,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        )

    def test_cli_requires_explicit_today_and_policy(self):
        result = self.run_cli([VACANCY])
        self.assertNotEqual(0, result.returncode)
        self.assertIn("today, policy and vacancies", result.stderr)

    def test_cli_uses_config_policy(self):
        result = self.run_cli({"today": "2026-08-26", "policy": POLICY, "vacancies": [VACANCY]})
        self.assertEqual(0, result.returncode, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual(["Senior WordPress Developer"], [row["title"] for row in rows])

        stricter = {**POLICY, "min_monthly_salary_eur": 5000}
        result = self.run_cli({"today": "2026-08-26", "policy": stricter, "vacancies": [VACANCY]})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
