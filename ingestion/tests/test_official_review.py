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

    def test_existing_engine_is_the_only_ranking_authority(self):
        # Nothing passes without complete supplied, verified signals.
        self.assertEqual(rank_fully_verified([], policy=POLICY, today=TODAY), [])


    def test_complete_evidence_can_reach_existing_deterministic_ranking(self):
        from vacature_ingestion.official_review import _FINAL_GATES

        url = "https://job-boards.greenhouse.io/example/jobs/987654"
        proof = {name: {"state": "verified", "source_ref": "official:review"}
                 for name in _FINAL_GATES}
        proof["exact_official_open_role"]["source_ref"] = url
        proof["original_posting_date"].update({"source_ref": url, "date": "2026-10-19"})
        item = {
            "title": "WordPress Developer", "employer": "Example",
            "canonical_url": url, "official_url": url,
            "posted_date": "2026-10-19", "fully_remote": True,
            "geography_compatible": True, "wordpress_related": True,
            "central_hard_mismatch": False, "listing_language": "en",
            "application_language": "en", "required_languages": [],
            "salary_monthly_eur": None, "core_fit": 50,
            "evidence_fit": 25, "workstyle_fit": 15,
            "verification": proof,
            "candidate_evidence_ids": ["active-verified-1"],
            "anchor_provenance": {
                "core_fit": [url], "evidence_fit": ["active-verified-1"],
                "workstyle_fit": ["active-verified-1"],
            },
        }
        ranked = rank_fully_verified(
            [item], policy=POLICY, today=TODAY,
            active_evidence_ids={"active-verified-1"}, prior_role_urls=set(),
        )
        self.assertEqual(1, len(ranked))
        self.assertEqual(100, ranked[0]["score"])
        self.assertNotIn("candidate_evidence_ids", ranked[0])
        self.assertNotIn("verification", ranked[0])
        self.assertNotIn("anchor_provenance", ranked[0])

        # Every hard gate matters; unknown is NEVER a pass or a score.
        for key in _FINAL_GATES:
            with self.subTest(missing_gate=key):
                changed = {**item, "verification": {k: dict(v) for k, v in proof.items()}}
                changed["verification"][key]["state"] = "unknown"
                self.assertEqual([], rank_fully_verified(
                    [changed], policy=POLICY, today=TODAY,
                    active_evidence_ids={"active-verified-1"}, prior_role_urls=set(),
                ))

        self.assertEqual([], rank_fully_verified(
            [item], policy=POLICY, today=TODAY,
            active_evidence_ids={"active-verified-1"}, prior_role_urls={url},
        ))
        self.assertEqual([], rank_fully_verified(
            [item], policy=POLICY, today=TODAY,
            active_evidence_ids=set(), prior_role_urls=set(),
        ))
        self.assertEqual([], rank_fully_verified([item], policy=POLICY, today=TODAY))

    def test_rank_rejects_unverified_date_and_provenance(self):
        from vacature_ingestion.official_review import _FINAL_GATES

        url = "https://job-boards.greenhouse.io/example/jobs/987654"
        gates = {key: {"state": "verified", "source_ref": url} for key in _FINAL_GATES}
        gates["original_posting_date"]["date"] = "2026-10-19"
        valid = {
            "title": "WordPress Developer", "employer": "Example",
            "canonical_url": url, "official_url": url,
            "posted_date": "2026-10-19", "fully_remote": True,
            "geography_compatible": True, "wordpress_related": True,
            "central_hard_mismatch": False, "listing_language": "en",
            "application_language": "en", "required_languages": [],
            "core_fit": 50, "evidence_fit": 25, "workstyle_fit": 15,
            "verification": gates, "candidate_evidence_ids": ["cv-1"],
            "anchor_provenance": {
                "core_fit": [url], "evidence_fit": ["cv-1"],
                "workstyle_fit": ["cv-1"],
            },
        }
        for changes in (
            {"posted_date": None},
            {"posted_date": "2026-10-10"},
            {"official_url": "https://evil.test/jobs/1"},
            {"candidate_evidence_ids": ["unverified"]},
            {"anchor_provenance": {"core_fit": [url], "evidence_fit": ["cv-1"], "workstyle_fit": []}},
            {"central_hard_mismatch": True},
        ):
            with self.subTest(changes=changes):
                candidate = {**valid, **changes}
                self.assertEqual([], rank_fully_verified(
                    [candidate], policy=POLICY, today=TODAY,
                    active_evidence_ids={"cv-1"}, prior_role_urls=set(),
                ))


if __name__ == "__main__":
    unittest.main()
