"""No-network regression tests for conservative official vacancy review."""
from datetime import date
import unittest

from vacature_engine.simple import policy_from_config
from vacature_ingestion.official_review import (
    assess_official_observation, geography_signal, rank_fully_verified,
)

POLICY = policy_from_config({
    "min_monthly_salary_eur": "3500", "max_posting_age_days": "7",
    "max_output_roles": "5", "min_output_score": "75",
    "min_core_fit": "40", "min_evidence_fit": "10",
    "allowed_listing_languages": "nl,en",
    "target_role_families": "wordpress_ecosystem,ai_workflow_automation,web_design_development",
})
TODAY = date(2026, 10, 19)
EVIDENCE = [
    {"evidence_id": "cv-wp", "source_type": "canonical_cv", "claim": "Developed WordPress, WooCommerce and Gutenberg websites", "active": "TRUE", "confidence": "high"},
    {"evidence_id": "cv-qa", "source_type": "canonical_cv", "claim": "Built Playwright tests and accessibility scripts", "active": "TRUE", "confidence": "high"},
    {"evidence_id": "outdated", "source_type": "canonical_cv", "claim": "WordPress administrator", "active": "FALSE", "confidence": "high"},
]
CANDIDATE = {"role_family_hints": ["wordpress_ecosystem"]}


def official(location="Remote - Costa Rica", **changes):
    row = {
        "source_id": "greenhouse",
        "source_type": "ats",
        "source_instance": "greenhouse:acquia",
        "canonical_url": "https://job-boards.greenhouse.io/acquia/jobs/8205142",
        "employer": "Acquia", "title": "WordPress Developer",
        "location": location, "workplace_type": "remote",
        "remote": True, "description": "Build WordPress and WooCommerce plugins.",
        "published_at": None, "listing_language": None,
        "source_metadata": {"provider": "greenhouse", "provider_job_id": 8205142},
    }
    row.update(changes)
    return row


class OfficialReviewTests(unittest.TestCase):
    def test_restricted_country_is_not_netherlands(self):
        for country in ("Remote - Costa Rica", "Remote United States", "India only",
                        "LATAM", "Australia", "US only"):
            with self.subTest(country=country):
                self.assertEqual(geography_signal(country), "restricted")
        self.assertEqual(geography_signal("Remote"), "unknown")

    def test_eu_explicitly_includes_netherlands(self):
        self.assertEqual(geography_signal("European Union; Serbia; Turkey"), "allowed")
        self.assertEqual(geography_signal("Netherlands"), "allowed")
        self.assertEqual(geography_signal("Worldwide"), "allowed")
        self.assertEqual(geography_signal("Remote - Spain"), "unknown")

    def test_only_live_known_ats_is_official(self):
        checks, ranked = assess_official_observation(
            official(), candidate=CANDIDATE, active_ids={"greenhouse"},
            evidence=EVIDENCE, policy=POLICY, today=TODAY,
        )
        self.assertEqual(checks["official_role"], "confirmed_current_public_ats")
        self.assertEqual(checks["role_open"], "present_in_live_official_feed")
        self.assertEqual(checks["netherlands"], "restricted")
        self.assertIsNone(ranked)

    def test_search_result_on_same_ats_hostname_is_not_official(self):
        row = official(location="European Union", source_id="google-jobs",
                       source_type="discovery")
        checks, rankable = assess_official_observation(
            row, candidate=CANDIDATE, active_ids={"google-jobs", "greenhouse"},
            evidence=EVIDENCE, policy=POLICY, today=TODAY,
        )
        self.assertEqual(checks["official_role"], "unverified")
        self.assertIsNone(rankable)

    def test_provider_identity_is_checked(self):
        for fake in (
            official(source_metadata={"provider": "lever"}),
            official(canonical_url="https://evil.test/acquia/jobs/8205142"),
        ):
            with self.subTest(fake=fake):
                status, _ = assess_official_observation(
                    fake, candidate=CANDIDATE, active_ids={"greenhouse"},
                    evidence=EVIDENCE, policy=POLICY, today=TODAY,
                )
                self.assertEqual(status["official_role"], "unverified")

    def test_explicit_remote_eu_still_needs_language_and_fit(self):
        checks, ranked = assess_official_observation(
            official(location="Remote - European Union", published_at="2026-10-18T00:00:00Z"),
            candidate=CANDIDATE, active_ids={"greenhouse"},
            evidence=EVIDENCE, policy=POLICY, today=TODAY,
        )
        self.assertEqual(checks["netherlands"], "allowed")
        self.assertEqual(checks["remote"], "confirmed")
        self.assertEqual(checks["original_publication"], "unknown")
        self.assertEqual(checks["fit_evidence"], "supported_claims_available")
        self.assertEqual(checks["evidence_claims_count"], 1)
        self.assertEqual(checks["language"], "unknown")
        self.assertIsNone(ranked)

    def test_old_explicit_publication_is_not_current(self):
        checks, _ = assess_official_observation(
            official(location="Remote - Europe", published_at="2026-08-01"),
            candidate=CANDIDATE, active_ids={"greenhouse"},
            evidence=EVIDENCE, policy=POLICY, today=TODAY,
        )
        self.assertEqual(checks["original_publication"], "too_old")

    def test_official_false_remote_does_not_pass(self):
        checks, _ = assess_official_observation(
            official(location="London", remote=False, workplace_type="hybrid"),
            candidate=CANDIDATE, active_ids={"greenhouse"},
            evidence=EVIDENCE, policy=POLICY, today=TODAY,
        )
        self.assertEqual(checks["remote"], "not_remote")
        self.assertEqual(checks["netherlands"], "unknown")

    def test_existing_engine_is_the_only_ranking_authority(self):
        # Nothing passes without complete supplied, verified signals.
        self.assertEqual(rank_fully_verified([], policy=POLICY, today=TODAY), [])


if __name__ == "__main__":
    unittest.main()
