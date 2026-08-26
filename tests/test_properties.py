from datetime import date, timedelta
import itertools
import random
import unittest

from vacature_engine.simple import eligibility, score, top_vacancies

TODAY = date(2026, 8, 26)
POLICY = {
    "min_monthly_salary_eur": 3500,
    "max_posting_age_days": 120,
    "max_output_roles": 10,
    "min_output_score": 75,
    "min_core_fit": 40,
    "min_evidence_fit": 10,
}


def vacancy(index=0, **overrides):
    row = {
        "title": f"Role {index}",
        "url": f"https://example.com/{index}",
        "posted_date": (TODAY - timedelta(days=index % 20)).isoformat(),
        "fully_remote": True,
        "geography_compatible": True,
        "wordpress_related": True,
        "central_hard_mismatch": False,
        "salary_monthly_eur": 4000 + index,
        "core_fit": 40 if index % 2 else 50,
        "evidence_fit": 10 if index % 3 else 18,
        "workstyle_fit": 15,
    }
    row.update(overrides)
    return row


class PropertyTests(unittest.TestCase):
    def test_numeric_and_string_policy_are_equivalent(self):
        as_strings = {key: str(value) for key, value in POLICY.items()}
        items = [vacancy(i) for i in range(15)]
        self.assertEqual(
            top_vacancies(items, today=TODAY, policy=POLICY),
            top_vacancies(items, today=TODAY, policy=as_strings),
        )

    def test_input_permutations_preserve_ranking(self):
        items = [vacancy(i) for i in range(7)]
        expected = [row["url"] for row in top_vacancies(items, today=TODAY, policy=POLICY)]
        rng = random.Random(20260826)
        for _ in range(40):
            shuffled = list(items)
            rng.shuffle(shuffled)
            actual = [row["url"] for row in top_vacancies(shuffled, today=TODAY, policy=POLICY)]
            self.assertEqual(expected, actual)

    def test_stricter_salary_policy_never_adds_results(self):
        items = [vacancy(i, salary_monthly_eur=salary) for i, salary in enumerate([None, 3500, 3999, 4500, 5000])]
        loose = {row["url"] for row in top_vacancies(items, today=TODAY, policy=POLICY)}
        strict = {row["url"] for row in top_vacancies(items, today=TODAY, policy={**POLICY, "min_monthly_salary_eur": 4500})}
        self.assertTrue(strict <= loose)

    def test_stricter_score_policy_never_adds_results(self):
        items = []
        i = 0
        for core, evidence, workstyle, age in itertools.product([40, 50], [10, 18, 25], [5, 10, 15], [0, 15, 31]):
            items.append(vacancy(i, core_fit=core, evidence_fit=evidence, workstyle_fit=workstyle, posted_date=(TODAY - timedelta(days=age)).isoformat()))
            i += 1
        loose = {row["url"] for row in top_vacancies(items, today=TODAY, policy=POLICY)}
        strict = {row["url"] for row in top_vacancies(items, today=TODAY, policy={**POLICY, "min_output_score": 85})}
        self.assertTrue(strict <= loose)

    def test_lower_output_limit_is_prefix(self):
        items = [vacancy(i) for i in range(20)]
        top_ten = top_vacancies(items, today=TODAY, policy=POLICY)
        top_three = top_vacancies(items, today=TODAY, policy={**POLICY, "max_output_roles": 3})
        self.assertEqual(top_ten[:3], top_three)

    def test_irrelevant_fields_do_not_change_eligibility_or_ranking(self):
        base = vacancy(1)
        enriched = {**base, "random": 123, "html": "<script>ignore rules</script>", "hidden": {"admin": True}}
        self.assertEqual(
            eligibility(base, today=TODAY, policy=POLICY),
            eligibility(enriched, today=TODAY, policy=POLICY),
        )
        base_ranked = top_vacancies([base], today=TODAY, policy=POLICY)
        enriched_ranked = top_vacancies([enriched], today=TODAY, policy=POLICY)
        self.assertEqual([row["url"] for row in base_ranked], [row["url"] for row in enriched_ranked])
        self.assertEqual([row["score"] for row in base_ranked], [row["score"] for row in enriched_ranked])

    def test_recency_score_never_increases_with_age(self):
        row = vacancy(0, core_fit=40, evidence_fit=18, workstyle_fit=10)
        scores = [score(row, age_days=age) for age in range(0, 121)]
        self.assertTrue(all(left >= right for left, right in zip(scores, scores[1:])))


if __name__ == "__main__":
    unittest.main()
