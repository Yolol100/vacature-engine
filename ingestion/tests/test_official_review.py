"""No-network regression tests for conservative official vacancy review."""
from datetime import date
import unittest

from vacature_engine.simple import policy_from_config
from vacature_ingestion.official_review import (
    assess_official_observation, discovery_region_conflict, geography_signal,
    rank_fully_verified,
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

    def test_europe_and_netherlands_exclusions_override_global_terms(self):
        for region in (
            "Worldwide excluding Netherlands",
            "Remote in Europe except Nederland",
            "EU, not hiring from the Netherlands",
            "Globally, no applicants from European Union",
        ):
            with self.subTest(region=region):
                self.assertEqual(geography_signal(region), "restricted")

    def test_real_board_geo_limited_roles_are_held_from_nl_review(self):
        for row in (
            {"source_type": "discovery_api", "source_id": "remotejobs-org",
             "location": "Philippines", "description": "Full-Stack WordPress Developer"},
            {"source_type": "job_board", "source_id": "remote-ok",
             "location": "Remote", "description":
                "We are exclusively considering applications from individuals "
                "currently residing in LATAM. Wordpress Developer."},
            {"source_type": "discovery_api", "source_id": "remotejobs-org",
             "location": "Colombia", "description": "WordPress Developer"},
            {"source_type": "job_board", "source_id": "remote-ok",
             "location": "Remote", "description":
                "Applicants must be based in the Philippines."},
        ):
            with self.subTest(source=row):
                self.assertIsNotNone(discovery_region_conflict(row))

    def test_board_marketing_mentions_and_positive_territories_are_not_exclusions(self):
        cases = [
            {"source_type": "job_board", "location": "Remote",
             "description": "Our office is in the Philippines. EU residents may apply."},
            {"source_type": "discovery_api", "location": "European Union",
             "description": "Candidates must be based in Philippines. "
                            "Our source location says the EU."},
            {"source_type": "job_board", "location": "Remote",
             "description": "Our LATAM customers love the WordPress platform."},
            {"source_type": "discovery_api", "location": "Worldwide",
             "description": "We serve customers in Australia."},
        ]
        for row in cases:
            with self.subTest(row=row):
                self.assertIsNone(discovery_region_conflict(row))

    def test_discovery_geo_never_proves_ats_employer_claim(self):
        row = {"source_type": "ats", "location": "Philippines",
               "description": "Only candidates in LATAM"}
        self.assertIsNone(discovery_region_conflict(row))

    def test_country_list_requires_every_restriction_to_be_outside_nl(self):
        limited = {"source_type": "discovery_api",
                   "source_metadata": {"location_restriction_names":
                                       ["Philippines", "Colombia"]}}
        mixed = {"source_type": "discovery_api",
                 "source_metadata": {"location_restriction_names":
                                     ["Philippines", "European Union"]}}
        self.assertEqual(discovery_region_conflict(limited),
                         "explicit_discovery_region_list")
        self.assertIsNone(discovery_region_conflict(mixed))

    def test_last_published_is_not_original_publication_date(self):
        result, _ = assess_official_observation(
            official(location="Remote - EU", published_at="2026-10-19T10:00:00Z"),
            candidate=CANDIDATE, active_ids={"greenhouse"},
            evidence=EVIDENCE, policy=POLICY, today=TODAY,
        )
        self.assertEqual(result["original_publication"], "unknown")

    def test_archived_library_cv_is_counted_only_with_valid_provenance(self):
        evidence = {
            "evidence_id": "library-wp",
            "source_type": "library_cv",
            "source_ref": "file_" + "0" * 32,
            "source_locator": "Experience > WordPress Plugin Development",
            "claim": "Developed WordPress plugins for clients",
            "active": "TRUE",
            "confidence": "high",
        }

        def indicator(item):
            signal, rankable = assess_official_observation(
                official(location="Remote - European Union"),
                candidate=CANDIDATE, active_ids={"greenhouse"},
                evidence=[item], policy=POLICY, today=TODAY)
            self.assertIsNone(rankable)
            return signal["evidence_claims_count"]

        self.assertEqual(indicator(evidence), 1)
        for changes in (
            {"source_ref": "file_invalid"},
            {"source_ref": "https://example.test/cv"},
            {"source_locator": ""},
            {"claim": "No experience with WordPress plugins"},
            {"active": "FALSE"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(indicator({**evidence, **changes}), 0)

    def test_negative_cv_claim_cannot_support_broad_fit_indicator(self):
        row = {
            "evidence_id": "neg-wp",
            "source_type": "canonical_cv",
            "claim": "No experience with WordPress, WooCommerce or Gutenberg.",
            "active": "TRUE",
            "confidence": "high",
        }
        checks, _ = assess_official_observation(
            official(location="Remote - European Union"),
            candidate=CANDIDATE, active_ids={"greenhouse"},
            evidence=[row], policy=POLICY, today=TODAY,
        )
        self.assertEqual(checks["evidence_claims_count"], 0)
        self.assertEqual(checks["fit_evidence"], "unverified")

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

    def test_rank_helper_must_reject_unverified_precalculated_scores(self):
        # Reproducer: engine eligibility is not official employer/ATS proof.
        # A complete-looking ranking payload is still not a validated assessment.
        item = {
            "title": "WordPress Developer",
            "employer": "Synthetic Employer",
            "canonical_url": "https://jobs.ashbyhq.com/synthetic/role-123",
            "posted_date": "2026-10-19",
            "fully_remote": True,
            "geography_compatible": True,
            "role_families": ["wordpress_ecosystem"],
            "central_hard_mismatch": False,
            "listing_language": "en",
            "application_language": "en",
            "required_languages": [],
            "core_fit": 40,
            "evidence_fit": 25,
            "workstyle_fit": 10,
            "authenticity": "verified",
            "role_open": True,
        }
        self.assertEqual([], rank_fully_verified([item], policy=POLICY, today=TODAY))
        self.assertEqual([], rank_fully_verified(
            [{**item, "verification": {"reviewed_on": TODAY.isoformat()}}],
            policy=POLICY, today=TODAY,
        ))

    def test_rank_helper_rejects_stale_or_incomplete_validated_handoffs(self):
        # A same-process handoff still needs today's complete digest context.
        from vacature_ingestion.official_review import _ValidatedRankingInput
        sha = "a" * 64
        data = {
            "title": "WordPress Developer", "employer": "Synthetic Employer",
            "canonical_url": "https://jobs.ashbyhq.com/synthetic/role-123",
            "posted_date": "2026-10-19", "fully_remote": True,
            "geography_compatible": True, "role_families": ["wordpress_ecosystem"],
            "central_hard_mismatch": False, "listing_language": "en",
            "application_language": "en", "required_languages": [],
            "core_fit": 40, "evidence_fit": 25, "workstyle_fit": 10,
            "authenticity": "verified", "role_open": True,
            "verification": {
                "assessment_sha256": sha, "policy_sha256": sha,
                "candidate_evidence_sha256": sha, "observation_sha256": sha,
                "official_page_sha256": sha, "reviewed_on": "2026-10-18",
                "requirements": 2, "mandatory_requirements": 1,
            },
        }
        self.assertEqual([], rank_fully_verified(
            [_ValidatedRankingInput(data)], policy=POLICY, today=TODAY,
        ))
        data["verification"]["reviewed_on"] = TODAY.isoformat()
        data["verification"]["policy_sha256"] = "not-a-digest"
        self.assertEqual([], rank_fully_verified(
            [_ValidatedRankingInput(data)], policy=POLICY, today=TODAY,
        ))
        data["verification"]["policy_sha256"] = sha
        data["verification"]["requirements"] = 0
        self.assertEqual([], rank_fully_verified(
            [_ValidatedRankingInput(data)], policy=POLICY, today=TODAY,
        ))

    def test_existing_engine_is_the_only_ranking_authority(self):
        # Nothing passes without complete supplied, verified signals.
        self.assertEqual(rank_fully_verified([], policy=POLICY, today=TODAY), [])


if __name__ == "__main__":
    unittest.main()
