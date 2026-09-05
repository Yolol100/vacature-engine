from datetime import date
import unittest

from vacature_engine.simple import eligibility, policy_from_config, top_vacancies

TODAY = date(2026, 8, 30)
POLICY = {
    "min_monthly_salary_eur": 3500,
    "max_posting_age_days": 120,
    "max_output_roles": 10,
    "min_output_score": 75,
    "min_core_fit": 40,
    "min_evidence_fit": 10,
    "allowed_listing_languages": "nl,en",
}


def vacancy(**overrides):
    row = {
        "title": "WordPress Developer",
        "url": "https://example.com/job",
        "posted_date": "2026-08-30",
        "fully_remote": True,
        "geography_compatible": True,
        "wordpress_related": True,
        "central_hard_mismatch": False,
        "listing_language": "en",
        "application_language": "en",
        "required_languages": [],
        "salary_monthly_eur": 4500,
        "core_fit": 50,
        "evidence_fit": 18,
        "workstyle_fit": 15,
    }
    row.update(overrides)
    return row


class LanguagePolicyTests(unittest.TestCase):
    def test_dutch_and_english_pass(self):
        self.assertTrue(eligibility(vacancy(), today=TODAY, policy=POLICY)["pass"])
        dutch = vacancy(listing_language="Nederlands", application_language="nl-NL")
        self.assertTrue(eligibility(dutch, today=TODAY, policy=POLICY)["pass"])

    def test_other_listing_language_fails(self):
        gate = eligibility(vacancy(listing_language="German"), today=TODAY, policy=POLICY)
        self.assertFalse(gate["pass"])
        self.assertIn("listing_language_not_allowed", gate["reasons"])

    def test_other_application_language_fails(self):
        gate = eligibility(vacancy(application_language="fr"), today=TODAY, policy=POLICY)
        self.assertFalse(gate["pass"])
        self.assertIn("application_language_not_allowed", gate["reasons"])

    def test_required_third_language_fails(self):
        gate = eligibility(vacancy(required_languages=["English", "German"]), today=TODAY, policy=POLICY)
        self.assertFalse(gate["pass"])
        self.assertIn("required_language_not_allowed", gate["reasons"])

    def test_required_language_evidence_must_be_explicit(self):
        missing = vacancy()
        missing.pop("required_languages")
        cases = [missing, vacancy(required_languages=None), vacancy(required_languages="")]
        for item in cases:
            with self.subTest(required_languages=item.get("required_languages", "<missing>")):
                gate = eligibility(item, today=TODAY, policy=POLICY)
                self.assertFalse(gate["pass"])
                self.assertIn("required_languages_invalid", gate["reasons"])

        self.assertTrue(eligibility(vacancy(required_languages=[]), today=TODAY, policy=POLICY)["pass"])

    def test_missing_language_evidence_fails_closed_when_gate_enabled(self):
        missing_listing = eligibility(vacancy(listing_language=None), today=TODAY, policy=POLICY)
        missing_application = eligibility(vacancy(application_language=None), today=TODAY, policy=POLICY)
        self.assertIn("listing_language_missing", missing_listing["reasons"])
        self.assertIn("application_language_missing", missing_application["reasons"])

    def test_missing_language_policy_fails_closed(self):
        config = dict(POLICY)
        config.pop("allowed_listing_languages")
        with self.assertRaisesRegex(ValueError, "allowed_listing_languages"):
            policy_from_config(config)

    def test_invalid_language_policy_fails_closed(self):
        with self.assertRaises(ValueError):
            policy_from_config({**POLICY, "allowed_listing_languages": "nl,english-only"})

    def test_policy_normalizes_language_aliases(self):
        policy = policy_from_config({**POLICY, "allowed_listing_languages": ["Nederlands", "English"]})
        self.assertEqual(frozenset({"nl", "en"}), policy.allowed_listing_languages)

    def test_top_vacancies_filters_language_before_ranking(self):
        rows = [vacancy(title="English"), vacancy(title="German", listing_language="de")]
        ranked = top_vacancies(rows, today=TODAY, policy=POLICY)
        self.assertEqual(["English"], [row["title"] for row in ranked])


if __name__ == "__main__":
    unittest.main()
