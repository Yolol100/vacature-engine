import unittest

from vacature_engine.core import canonical_url, content_hash, vacancy_id
from vacature_engine.policy import application_guard, hard_gate, score


class SkillParityVectors(unittest.TestCase):
    def test_identity_vector(self):
        self.assertEqual(canonical_url("https://Example.com/jobs/1/?utm_source=x&a=2"), "https://example.com/jobs/1?a=2")
        self.assertEqual(vacancy_id("Acme", "Senior Dev", "https://x.test/1?utm_source=a"), vacancy_id("acme", "Senior Dev", "https://x.test/1"))
        self.assertEqual(content_hash("HELLO   world"), content_hash("hello world"))

    def test_gate_vector(self):
        data = {"posted_age_days": 2, "active": True, "official_link_working": True, "fully_remote": True, "netherlands_eligibility": "allowed", "level": "Senior Engineer", "central_hard_mismatch_count": 0}
        self.assertEqual(hard_gate(data), {"pass": True, "reasons": []})

    def test_application_vector(self):
        data = {"stage": "prepare", "user_explicitly_requested": True, "final_verification_pass": True, "hard_gate_pass": True}
        self.assertEqual(application_guard(data), {"pass": True, "stage": "prepare", "reasons": []})

    def test_score_vector(self):
        data = {"hard_requirements": 35, "experience_seniority": 20, "cv_portfolio_evidence": 15, "wordpress_stack": 10, "quality_stack": 10, "communication_autonomy": 5, "preferred_requirements": 5, "freshness": 15, "competition": 10, "netherlands_certainty": 10, "employer_credibility": 5, "compensation_contract_fit": 5, "central_hard_missing": False, "multiple_central_hard_mismatches": False}
        self.assertEqual(score(data)["match_score"], 100.0)
        self.assertEqual(score(data)["opportunity_score"], 100.0)


if __name__ == "__main__":
    unittest.main()
