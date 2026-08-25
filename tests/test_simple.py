from datetime import date, timedelta
import unittest

from vacature_engine.simple import choose_language, eligibility, top_vacancies

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
        "core_fit": 45,
        "evidence_fit": 22,
        "workstyle_fit": 13,
    }
    data.update(overrides)
    return data


class SimplePolicyTests(unittest.TestCase):
    def test_good_vacancy_passes(self):
        self.assertTrue(eligibility(vacancy(), today=TODAY)["pass"])

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

    def test_unknown_salary_is_strong_match_fallback(self):
        known = vacancy(title="Known", salary_monthly_eur=4000, core_fit=35)
        strong_unknown = vacancy(title="Strong Unknown", salary_monthly_eur=None, core_fit=50)
        weak_unknown = vacancy(
            title="Weak Unknown",
            salary_monthly_eur=None,
            core_fit=30,
            evidence_fit=15,
            workstyle_fit=10,
        )
        ranked = top_vacancies([strong_unknown, weak_unknown, known], today=TODAY)
        self.assertEqual(["Known", "Strong Unknown"], [row["title"] for row in ranked])

    def test_ranking_prefers_better_fit(self):
        strong = vacancy(title="Strong", core_fit=49, evidence_fit=24, workstyle_fit=14)
        weak = vacancy(title="Weak", core_fit=30, evidence_fit=15, workstyle_fit=10)
        ranked = top_vacancies([weak, strong], today=TODAY)
        self.assertEqual("Strong", ranked[0]["title"])

    def test_top_ten_limit(self):
        items = [vacancy(title=f"Role {i}") for i in range(12)]
        self.assertEqual(10, len(top_vacancies(items, today=TODAY)))

    def test_invalid_score_component_raises(self):
        with self.assertRaises(ValueError):
            top_vacancies([vacancy(core_fit=51)], today=TODAY)

    def test_language_priority(self):
        self.assertEqual("nl", choose_language(vacancy_language="Nederlands"))
        self.assertEqual("en", choose_language(form_language="English", vacancy_language="Nederlands"))
        self.assertEqual("de", choose_language(explicit_language="de", form_language="English"))


if __name__ == "__main__":
    unittest.main()
