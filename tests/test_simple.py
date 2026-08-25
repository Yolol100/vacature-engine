from datetime import date, timedelta
import unittest

from vacature_engine.simple import choose_language, eligibility, score, top_vacancies

TODAY = date(2026, 8, 25)


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
        self.assertTrue(eligibility(vacancy(), today=TODAY)["pass"])
        self.assertEqual(1, len(top_vacancies([vacancy()], today=TODAY)))

    def test_today_is_required(self):
        with self.assertRaises(TypeError):
            eligibility(vacancy())
        with self.assertRaises(TypeError):
            top_vacancies([vacancy()])

        amsterdam_today = date(2026, 8, 26)
        same_day = vacancy(posted_date=amsterdam_today.isoformat())
        self.assertTrue(eligibility(same_day, today=amsterdam_today)["pass"])
        self.assertEqual(1, len(top_vacancies([same_day], today=amsterdam_today)))

    def test_hard_filters(self):
        cases = [
            vacancy(fully_remote=False),
            vacancy(geography_compatible=False),
            vacancy(wordpress_related=False),
            vacancy(central_hard_mismatch=True),
            vacancy(salary_monthly_eur=3499),
            vacancy(posted_date="2025-12-31"),
            vacancy(posted_date="2026-04-26"),
        ]
        for item in cases:
            with self.subTest(item=item):
                self.assertFalse(eligibility(item, today=TODAY)["pass"])

    def test_age_boundary(self):
        at_limit = vacancy(posted_date=(TODAY - timedelta(days=120)).isoformat())
        too_old = vacancy(posted_date=(TODAY - timedelta(days=121)).isoformat())
        self.assertTrue(eligibility(at_limit, today=TODAY)["pass"])
        self.assertFalse(eligibility(too_old, today=TODAY)["pass"])

    def test_recency_anchors(self):
        expected = {0: 78, 14: 78, 15: 76, 30: 76, 31: 74, 60: 74, 61: 72, 90: 72, 91: 70, 120: 70}
        for age_days, expected_score in expected.items():
            item = vacancy(posted_date=(TODAY - timedelta(days=age_days)).isoformat())
            self.assertEqual(expected_score, score(item, age_days=age_days))

    def test_only_strong_matches_are_output(self):
        weak_score = vacancy(title="Weak score", core_fit=40, evidence_fit=10, workstyle_fit=5, posted_date=(TODAY - timedelta(days=31)).isoformat())
        weak_core = vacancy(title="Weak core", core_fit=25, evidence_fit=25, workstyle_fit=15)
        weak_evidence = vacancy(title="Weak evidence", core_fit=50, evidence_fit=0, workstyle_fit=15)
        self.assertEqual([], top_vacancies([weak_score, weak_core, weak_evidence], today=TODAY))

    def test_score_75_boundary_passes(self):
        item = vacancy(core_fit=40, evidence_fit=10, workstyle_fit=15, posted_date=TODAY.isoformat())
        ranked = top_vacancies([item], today=TODAY)
        self.assertEqual(75, ranked[0]["score"])

    def test_unknown_salary_is_strong_match_fallback(self):
        weak_known = vacancy(title="Weak Known", salary_monthly_eur=4000, core_fit=25, evidence_fit=10, workstyle_fit=5)
        strong_unknown = vacancy(title="Strong Unknown", salary_monthly_eur=None, core_fit=50, evidence_fit=18, workstyle_fit=10)
        weak_unknown = vacancy(title="Weak Unknown", salary_monthly_eur=None, core_fit=25, evidence_fit=10, workstyle_fit=5)
        ranked = top_vacancies([strong_unknown, weak_unknown, weak_known], today=TODAY)
        self.assertEqual(["Strong Unknown"], [row["title"] for row in ranked])

    def test_ranking_prefers_better_fit(self):
        strong = vacancy(title="Strong", core_fit=50, evidence_fit=25, workstyle_fit=15)
        adequate = vacancy(title="Adequate", core_fit=40, evidence_fit=10, workstyle_fit=15)
        ranked = top_vacancies([adequate, strong], today=TODAY)
        self.assertEqual(["Strong", "Adequate"], [row["title"] for row in ranked])

    def test_tie_break_prefers_core_then_evidence(self):
        higher_core = vacancy(title="Higher Core", core_fit=50, evidence_fit=10, workstyle_fit=5)
        lower_core = vacancy(title="Lower Core", core_fit=40, evidence_fit=10, workstyle_fit=15)
        self.assertEqual("Higher Core", top_vacancies([lower_core, higher_core], today=TODAY)[0]["title"])

        higher_evidence = vacancy(title="Higher Evidence", core_fit=40, evidence_fit=25, workstyle_fit=0)
        lower_evidence = vacancy(title="Lower Evidence", core_fit=40, evidence_fit=10, workstyle_fit=15)
        self.assertEqual("Higher Evidence", top_vacancies([lower_evidence, higher_evidence], today=TODAY)[0]["title"])

    def test_top_ten_limit(self):
        items = [vacancy(title=f"Role {i}") for i in range(12)]
        self.assertEqual(10, len(top_vacancies(items, today=TODAY)))

    def test_non_anchor_score_component_raises(self):
        with self.assertRaises(ValueError):
            top_vacancies([vacancy(core_fit=45)], today=TODAY)

    def test_language_priority(self):
        self.assertEqual("nl", choose_language(vacancy_language="Nederlands"))
        self.assertEqual("en", choose_language(form_language="English", vacancy_language="Nederlands"))
        self.assertEqual("de", choose_language(explicit_language="de", form_language="English"))


if __name__ == "__main__":
    unittest.main()
