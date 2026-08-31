from datetime import date
import math
import unittest

from vacature_engine.simple import eligibility, top_vacancies

POLICY = {
    "min_monthly_salary_eur": 3500,
    "max_posting_age_days": 0,
    "max_output_roles": 10,
    "min_output_score": 75,
    "min_core_fit": 40,
    "min_evidence_fit": 10,
}
TODAY = date(2027, 1, 1)


def vacancy(**overrides):
    row = {
        "title": "WordPress Developer",
        "url": "https://example.com/job",
        "posted_date": "2026-12-31",
        "fully_remote": True,
        "geography_compatible": True,
        "wordpress_related": True,
        "central_hard_mismatch": False,
        "salary_monthly_eur": 4500,
        "core_fit": 50,
        "evidence_fit": 18,
        "workstyle_fit": 15,
    }
    row.update(overrides)
    return row


class GlobalRemotePolicyTests(unittest.TestCase):
    def test_cross_year_vacancy_passes_without_age_limit(self):
        self.assertTrue(eligibility(vacancy(), today=TODAY, policy=POLICY)["pass"])

    def test_foreign_employer_does_not_require_netherlands_wording(self):
        item = vacancy(employer_country="United States", listing_country="United Kingdom", country_allowed="Worldwide")
        self.assertTrue(eligibility(item, today=TODAY, policy=POLICY)["pass"])

    def test_global_discovery_still_rejects_incompatible_geography(self):
        gate = eligibility(vacancy(geography_compatible=False), today=TODAY, policy=POLICY)
        self.assertFalse(gate["pass"])
        self.assertIn("country_restriction", gate["reasons"])

    def test_salary_range_that_reaches_preference_passes(self):
        item = vacancy(salary_monthly_eur=None, salary_min_monthly_eur=3000, salary_max_monthly_eur=5500)
        gate = eligibility(item, today=TODAY, policy=POLICY)
        self.assertTrue(gate["pass"])
        self.assertTrue(gate["salary_known"])

    def test_salary_range_entirely_below_preference_warns(self):
        item = vacancy(salary_monthly_eur=None, salary_min_monthly_eur=2500, salary_max_monthly_eur=3499)
        gate = eligibility(item, today=TODAY, policy=POLICY)
        self.assertTrue(gate["pass"])
        self.assertIn("salary_below_preference", gate["warnings"])

    def test_invalid_or_conflicting_ranges_fail_closed(self):
        cases = [
            vacancy(salary_monthly_eur=None, salary_min_monthly_eur=5000, salary_max_monthly_eur=4000),
            vacancy(salary_monthly_eur=4500, salary_min_monthly_eur=4000, salary_max_monthly_eur=5000),
            vacancy(salary_monthly_eur=None, salary_min_monthly_eur="3000", salary_max_monthly_eur=5000),
            vacancy(salary_monthly_eur=None, salary_min_monthly_eur=3000, salary_max_monthly_eur=math.inf),
        ]
        for item in cases:
            with self.subTest(item=item):
                gate = eligibility(item, today=TODAY, policy=POLICY)
                self.assertFalse(gate["pass"])
                self.assertIn("salary_invalid", gate["reasons"])

    def test_known_salary_range_precedes_unknown_salary(self):
        known = vacancy(title="Known", salary_monthly_eur=None, salary_min_monthly_eur=3000, salary_max_monthly_eur=5500, core_fit=40, evidence_fit=10, workstyle_fit=15)
        unknown = vacancy(title="Unknown", salary_monthly_eur=None, core_fit=50, evidence_fit=25, workstyle_fit=15)
        ranked = top_vacancies([unknown, known], today=TODAY, policy=POLICY)
        self.assertEqual(["Known", "Unknown"], [row["title"] for row in ranked])


if __name__ == "__main__":
    unittest.main()
