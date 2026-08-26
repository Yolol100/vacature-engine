from datetime import date, timedelta
import math
import unittest

from vacature_engine.simple import (
    choose_language,
    eligibility,
    policy_from_config,
    score,
    top_vacancies,
)

TODAY = date(2026, 8, 26)
POLICY = {
    "min_monthly_salary_eur": 3500,
    "max_posting_age_days": 120,
    "max_output_roles": 10,
    "min_output_score": 75,
    "min_core_fit": 40,
    "min_evidence_fit": 10,
}


def vacancy(**overrides):
    data = {
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
    data.update(overrides)
    return data


class SimplePolicyTests(unittest.TestCase):
    def test_good_vacancy_passes(self):
        self.assertTrue(eligibility(vacancy(), today=TODAY, policy=POLICY)["pass"])
        self.assertEqual(1, len(top_vacancies([vacancy()], today=TODAY, policy=POLICY)))

    def test_today_and_policy_are_required(self):
        with self.assertRaises(TypeError):
            eligibility(vacancy(), policy=POLICY)
        with self.assertRaises(TypeError):
            top_vacancies([vacancy()], policy=POLICY)
        with self.assertRaises(TypeError):
            eligibility(vacancy(), today=TODAY)
        with self.assertRaises(TypeError):
            top_vacancies([vacancy()], today=TODAY)

    def test_policy_is_read_from_config_keys(self):
        policy = policy_from_config({key: str(value) for key, value in POLICY.items()})
        self.assertEqual(3500, policy.min_monthly_salary_eur)
        self.assertEqual(120, policy.max_posting_age_days)
        self.assertEqual(10, policy.max_output_roles)

    def test_missing_policy_key_fails_closed(self):
        broken = dict(POLICY)
        broken.pop("min_output_score")
        with self.assertRaises(ValueError):
            top_vacancies([vacancy()], today=TODAY, policy=broken)

    def test_config_salary_threshold_changes_behavior(self):
        self.assertTrue(eligibility(vacancy(salary_monthly_eur=4500), today=TODAY, policy=POLICY)["pass"])
        stricter = {**POLICY, "min_monthly_salary_eur": 5000}
        gate = eligibility(vacancy(salary_monthly_eur=4500), today=TODAY, policy=stricter)
        self.assertFalse(gate["pass"])
        self.assertIn("salary_below_minimum", gate["reasons"])

    def test_salary_floor_boundary(self):
        at_floor = vacancy(salary_monthly_eur=3500)
        below_floor = vacancy(salary_monthly_eur=3499.99)
        self.assertTrue(eligibility(at_floor, today=TODAY, policy=POLICY)["pass"])
        self.assertFalse(eligibility(below_floor, today=TODAY, policy=POLICY)["pass"])

    def test_config_age_and_output_limits_change_behavior(self):
        thirty_days = {**POLICY, "max_posting_age_days": 30}
        older = vacancy(posted_date=(TODAY - timedelta(days=31)).isoformat())
        self.assertFalse(eligibility(older, today=TODAY, policy=thirty_days)["pass"])

        top_three = {**POLICY, "max_output_roles": 3}
        items = [vacancy(title=f"Role {i}", url=f"https://example.com/{i}") for i in range(12)]
        self.assertEqual(3, len(top_vacancies(items, today=TODAY, policy=top_three)))

    def test_config_score_threshold_changes_behavior(self):
        item = vacancy(core_fit=40, evidence_fit=10, workstyle_fit=15, posted_date=TODAY.isoformat())
        self.assertEqual(75, top_vacancies([item], today=TODAY, policy=POLICY)[0]["score"])
        stricter = {**POLICY, "min_output_score": 76}
        self.assertEqual([], top_vacancies([item], today=TODAY, policy=stricter))

    def test_hard_filters(self):
        cases = [
            vacancy(fully_remote=False),
            vacancy(geography_compatible=False),
            vacancy(wordpress_related=False),
            vacancy(central_hard_mismatch=True),
            vacancy(salary_monthly_eur=3499),
            vacancy(posted_date="2025-12-31"),
            vacancy(posted_date="2026-04-27"),
        ]
        for item in cases:
            with self.subTest(item=item):
                self.assertFalse(eligibility(item, today=TODAY, policy=POLICY)["pass"])

    def test_current_year_is_dynamic(self):
        jan_2027 = date(2027, 1, 1)
        same_day = vacancy(posted_date="2027-01-01")
        old_year = vacancy(posted_date="2026-12-31")
        self.assertTrue(eligibility(same_day, today=jan_2027, policy=POLICY)["pass"])
        self.assertFalse(eligibility(old_year, today=jan_2027, policy=POLICY)["pass"])
        self.assertIn("not_current_year", eligibility(old_year, today=jan_2027, policy=POLICY)["reasons"])

    def test_age_boundary(self):
        at_limit = vacancy(posted_date=(TODAY - timedelta(days=120)).isoformat())
        too_old = vacancy(posted_date=(TODAY - timedelta(days=121)).isoformat())
        self.assertTrue(eligibility(at_limit, today=TODAY, policy=POLICY)["pass"])
        self.assertFalse(eligibility(too_old, today=TODAY, policy=POLICY)["pass"])

    def test_recency_anchors(self):
        expected = {0: 78, 14: 78, 15: 76, 30: 76, 31: 74, 60: 74, 61: 72, 90: 72, 91: 70, 120: 70}
        for age_days, expected_score in expected.items():
            item = vacancy(posted_date=(TODAY - timedelta(days=age_days)).isoformat())
            self.assertEqual(expected_score, score(item, age_days=age_days))

    def test_only_strong_matches_are_output(self):
        weak_score = vacancy(title="Weak score", core_fit=40, evidence_fit=10, workstyle_fit=5, posted_date=(TODAY - timedelta(days=31)).isoformat())
        weak_core = vacancy(title="Weak core", core_fit=25, evidence_fit=25, workstyle_fit=15)
        weak_evidence = vacancy(title="Weak evidence", core_fit=50, evidence_fit=0, workstyle_fit=15)
        self.assertEqual([], top_vacancies([weak_score, weak_core, weak_evidence], today=TODAY, policy=POLICY))

    def test_core_and_evidence_boundaries_pass(self):
        item = vacancy(core_fit=40, evidence_fit=10, workstyle_fit=15, posted_date=TODAY.isoformat())
        ranked = top_vacancies([item], today=TODAY, policy=POLICY)
        self.assertEqual(1, len(ranked))

    def test_score_75_boundary_passes(self):
        item = vacancy(core_fit=40, evidence_fit=10, workstyle_fit=15, posted_date=TODAY.isoformat())
        ranked = top_vacancies([item], today=TODAY, policy=POLICY)
        self.assertEqual(75, ranked[0]["score"])

    def test_unknown_salary_is_strong_match_fallback(self):
        weak_known = vacancy(title="Weak Known", salary_monthly_eur=4000, core_fit=25, evidence_fit=10, workstyle_fit=5)
        strong_unknown = vacancy(title="Strong Unknown", salary_monthly_eur=None, core_fit=50, evidence_fit=18, workstyle_fit=10)
        weak_unknown = vacancy(title="Weak Unknown", salary_monthly_eur=None, core_fit=25, evidence_fit=10, workstyle_fit=5)
        ranked = top_vacancies([strong_unknown, weak_unknown, weak_known], today=TODAY, policy=POLICY)
        self.assertEqual(["Strong Unknown"], [row["title"] for row in ranked])

    def test_invalid_salary_is_rejected_not_unknown(self):
        for salary in [math.nan, math.inf, -math.inf, True, "4500", object()]:
            with self.subTest(salary=salary):
                item = vacancy(salary_monthly_eur=salary, core_fit=50, evidence_fit=18, workstyle_fit=10)
                gate = eligibility(item, today=TODAY, policy=POLICY)
                self.assertFalse(gate["pass"])
                self.assertFalse(gate["salary_known"])
                self.assertIn("salary_invalid", gate["reasons"])
                self.assertEqual([], top_vacancies([item], today=TODAY, policy=POLICY))

    def test_known_salary_precedes_unknown_salary(self):
        known = vacancy(title="Known", salary_monthly_eur=4000, core_fit=40, evidence_fit=10, workstyle_fit=15)
        unknown = vacancy(title="Unknown", salary_monthly_eur=None, core_fit=50, evidence_fit=25, workstyle_fit=15)
        ranked = top_vacancies([unknown, known], today=TODAY, policy=POLICY)
        self.assertEqual(["Known", "Unknown"], [row["title"] for row in ranked])

    def test_ranking_prefers_better_fit(self):
        strong = vacancy(title="Strong", core_fit=50, evidence_fit=25, workstyle_fit=15)
        adequate = vacancy(title="Adequate", core_fit=40, evidence_fit=10, workstyle_fit=15)
        ranked = top_vacancies([adequate, strong], today=TODAY, policy=POLICY)
        self.assertEqual(["Strong", "Adequate"], [row["title"] for row in ranked])

    def test_tie_break_prefers_core_then_evidence_then_newer(self):
        higher_core = vacancy(title="Higher Core", core_fit=50, evidence_fit=10, workstyle_fit=5)
        lower_core = vacancy(title="Lower Core", core_fit=40, evidence_fit=10, workstyle_fit=15)
        self.assertEqual("Higher Core", top_vacancies([lower_core, higher_core], today=TODAY, policy=POLICY)[0]["title"])

        higher_evidence = vacancy(title="Higher Evidence", core_fit=40, evidence_fit=25, workstyle_fit=0)
        lower_evidence = vacancy(title="Lower Evidence", core_fit=40, evidence_fit=10, workstyle_fit=15)
        self.assertEqual("Higher Evidence", top_vacancies([lower_evidence, higher_evidence], today=TODAY, policy=POLICY)[0]["title"])

        newer = vacancy(title="Newer", posted_date=(TODAY - timedelta(days=1)).isoformat())
        older = vacancy(title="Older", posted_date=(TODAY - timedelta(days=2)).isoformat())
        self.assertEqual("Newer", top_vacancies([older, newer], today=TODAY, policy=POLICY)[0]["title"])

    def test_exact_ties_are_input_order_independent(self):
        items = [vacancy(title=f"Role {i}", url=f"https://example.com/{i}") for i in range(12)]
        forward = [row["url"] for row in top_vacancies(items, today=TODAY, policy=POLICY)]
        reverse = [row["url"] for row in top_vacancies(list(reversed(items)), today=TODAY, policy=POLICY)]
        self.assertEqual(forward, reverse)

    def test_bad_records_are_skipped_without_breaking_batch(self):
        bad_records = [
            None,
            "bad",
            123,
            vacancy(title="Bad anchor", core_fit=45),
            vacancy(title="Missing core", core_fit=None),
            vacancy(title="Infinite core", core_fit=math.inf),
        ]
        good = vacancy(title="Good")
        ranked = top_vacancies([*bad_records, good], today=TODAY, policy=POLICY)
        self.assertEqual(["Good"], [row["title"] for row in ranked])

    def test_score_still_rejects_non_anchor_when_called_directly(self):
        with self.assertRaises(ValueError):
            score(vacancy(core_fit=45), age_days=1)

    def test_language_priority(self):
        self.assertEqual("nl", choose_language(vacancy_language="Nederlands"))
        self.assertEqual("en", choose_language(form_language="English", vacancy_language="Nederlands"))
        self.assertEqual("de", choose_language(explicit_language="de", form_language="English"))


if __name__ == "__main__":
    unittest.main()
