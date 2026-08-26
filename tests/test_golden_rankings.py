from datetime import date
import json
from pathlib import Path
import unittest

from vacature_engine.simple import top_vacancies


class GoldenRankingTests(unittest.TestCase):
    def test_contract_golden_ranking(self):
        fixture_path = Path(__file__).parent / "fixtures" / "golden_rankings.json"
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        ranked = top_vacancies(data["vacancies"], today=date.fromisoformat(data["today"]), policy=data["policy"])
        self.assertEqual(data["expected_titles"], [row["title"] for row in ranked])


if __name__ == "__main__":
    unittest.main()
