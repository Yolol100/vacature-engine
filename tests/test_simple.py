from datetime import date, timedelta
import math
import unittest

from vacature_engine.simple import eligibility, policy_from_config, score, top_vacancies

TODAY = date(2026, 8, 31)
POLICY = {
    "min_monthly_salary_eur": 3500,
    "max_posting_age_days": 0,
    "max_output_roles": 10,
    "min_output_score": 75,
    "min_core_fit": 40,
    "min_evidence_fit": 10,
}


def vacancy(**overrides):
    data = {
        "title": "WordPress Web Developer",
        "url": "https://example.com/job",
        "posted_date": "2026-08-20",
        "fully_remote": True,
        "geography_compatible": True,
        "wordpress_related": True,
        "central_hard_mismatch": False,
        "salary_monthly_eur": 4500,
        "core_fit": 50,
        "evidence_fit": 18,
        "workstyle_fit": 10,
    }
    data.update(overrides)
    return data


class RemoteFirstPolicyTests(unittest.TestCase):
    def test_policy_zero_age_means_unlimited(self):
        item = vacancy(posted_date="2025-01-01")
        gate = eligibility(item, today=TODAY, policy=POLICY)
        self.assertTrue(gate["pass"])
        self.assertNotIn("older_than_max_age", gate["reasons"])

    def test_positive_age_limit_still_works(self):
        limited = {**POLICY, "max_posting_age_days": 30}
        item = vacancy(posted_date=(TODAY - timedelta(days=31)).isoformat())
        gate = eligibility(item, today=TODAY, policy=limited)
        self.assertFalse(gate["pass"])
        self.assertIn("older_than_max_age", gate["reasons"])

    def test_remote_remains_hard_gate(self):
        for item in [vacancy(fully_remote=False), vacancy(fully_remote=None)]:
            with self.subTest(item=item):
                gate = eligibility(item, today=TODAY, policy=POLICY)
                self.assertFalse(gate["pass"])
                self.assertIn("not_remote", gate["reasons"])

    def test_geography_compatibility_remains_hard_gate(self):
        gate = eligibility(vacancy(geography_compatible=False), today=TODAY, policy=POLICY)
        self.assertFalse(gate["pass"])
        self.assertIn("country_restriction", gate["reasons"])

    def test_wordpress_relationship_remains_required(self):
        gate = eligibility(vacancy(wordpress_related=False), today=TODAY, policy=POLICY)
        self.assertFalse(gate["pass"])
        self.assertIn("not_wordpress_related", gate["reasons"])

    def test_broader_wordpress_title_is_allowed(self):
        item = vacancy(title="Ecommerce Web Developer", wordpress_related=True)
        self.assertTrue(eligibility(item, today=TODAY, policy=POLICY)["pass"])

    def test_salary_below_preference_is_warning_not_rejection(self):
        gate = eligibility(vacancy(salary_monthly_eur=2500), today=TODAY, policy=POLICY)
        self.assertTrue(gate["pass"])
        self.assertIn("salary_below_preference", gate["warnings"])

    def test_unknown_salary_is_warning_not_rejection(self):
        gate = eligibility(vacancy(salary_monthly_eur=None), today=TODAY, policy=POLICY)
        self.assertTrue(gate["pass"])
        self.assertIn("salary_unknown", gate["warnings"])

    def test_invalid_salary_is_warning_not_rejection(self):
        for salary in [math.nan, math.inf, -math.inf, True, "4500", object()]:
            with self.subTest(salary=salary):
                gate = eligibility(vacancy(salary_monthly_eur=salary), today=TODAY, policy=POLICY)
                self.assertTrue(gate["pass"])
                self.assertIn("salary_invalid", gate["warnings"])

    def test_missing_date_is_warning_not_rejection(self):
        gate = eligibility(vacancy(posted_date=None), today=TODAY, policy=POLICY)
        self.assertTrue(gate["pass"])
        self.assertIn("date_missing", gate["warnings"])

    def test_future_date_still_rejected(self):
        gate = eligibility(vacancy(posted_date="2026-09-01"), today=TODAY, policy=POLICY)
        self.assertFalse(gate["pass"])
        self.assertIn("future_date", gate["reasons"])

    def test_missing_date_gets_low_recency_not_fresh_bonus(self):
        missing = vacancy(title="Missing date", posted_date=None)
        fresh = vacancy(title="Fresh", posted_date=TODAY.isoformat())
        ranked = top_vacancies([missing, fresh], today=TODAY, policy=POLICY)
        self.assertEqual("Fresh", ranked[0]["title"])
        self.assertLess(ranked[1]["score"], ranked[0]["score"])

    def test_salary_does_not_control_ranking(self):
        strong_unknown = vacancy(title="Strong Unknown", salary_monthly_eur=None, core_fit=50, evidence_fit=25, workstyle_fit=15)
        weaker_known = vacancy(title="Weaker Known", salary_monthly_eur=5000, core_fit=40, evidence_fit=10, workstyle_fit=15)
        ranked = top_vacancies([weaker_known, strong_unknown], today=TODAY, policy=POLICY)
        self.assertEqual("Strong Unknown", ranked[0]["title"])

    def test_score_anchors_unchanged(self):
        item = vacancy(core_fit=40, evidence_fit=10, workstyle_fit=15)
        self.assertEqual(75, score(item, age_days=0))
        with self.assertRaises(ValueError):
            score(vacancy(core_fit=45), age_days=0)

    def test_output_thresholds_remain(self):
        weak_core = vacancy(core_fit=25, evidence_fit=25, workstyle_fit=15)
        weak_evidence = vacancy(core_fit=50, evidence_fit=0, workstyle_fit=15)
        self.assertEqual([], top_vacancies([weak_core, weak_evidence], today=TODAY, policy=POLICY))

    def test_output_limit_remains(self):
        limited = {**POLICY, "max_output_roles": 3}
        items = [vacancy(title=f"Role {i}", url=f"https://example.com/{i}") for i in range(12)]
        self.assertEqual(3, len(top_vacancies(items, today=TODAY, policy=limited)))

    def test_policy_validation(self):
        parsed = policy_from_config({key: str(value) for key, value in POLICY.items()})
        self.assertEqual(0, parsed.max_posting_age_days)
        broken = dict(POLICY)
        broken.pop("min_output_score")
        with self.assertRaises(ValueError):
            policy_from_config(broken)


if __name__ == "__main__":
    unittest.main()
