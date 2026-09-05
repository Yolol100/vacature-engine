from datetime import date
import json
from pathlib import Path
import unittest

from vacature_engine.simple import eligibility, top_vacancies


class GoldenRankingTests(unittest.TestCase):
    def _fixture(self):
        fixture_path = Path(__file__).parent / "fixtures" / "golden_rankings.json"
        return json.loads(fixture_path.read_text(encoding="utf-8"))

    def test_contract_golden_ranking(self):
        data = self._fixture()
        ranked = top_vacancies(
            data["vacancies"],
            today=date.fromisoformat(data["today"]),
            policy=data["policy"],
        )
        self.assertEqual(data["expected_titles"], [row["title"] for row in ranked])

    def test_benchmark_gate_and_pre_labeled_cases(self):
        data = self._fixture()
        vacancies = data["vacancies"]
        expectations = data["expectations"]
        today = date.fromisoformat(data["today"])

        self.assertGreaterEqual(len(vacancies), 30, "ranking benchmark requires at least 30 cases")
        self.assertEqual(len(vacancies), len(expectations), "every benchmark case must be pre-labeled")

        ranked = top_vacancies(vacancies, today=today, policy=data["policy"])
        selected_titles = {row["title"] for row in ranked}

        for vacancy in vacancies:
            title = vacancy["title"]
            self.assertIn(title, expectations, f"missing pre-label for {title}")
            expected = expectations[title]
            gate = eligibility(vacancy, today=today, policy=data["policy"])
            self.assertEqual(expected["gate_pass"], gate["pass"], title)
            if expected.get("reason"):
                self.assertIn(expected["reason"], gate["reasons"], title)
            self.assertEqual(expected["selected"], title in selected_titles, title)


if __name__ == "__main__":
    unittest.main()
