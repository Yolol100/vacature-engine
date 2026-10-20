"""Offline integration tests: no Google calls, external sites or Register writes."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from vacature_engine.simple import policy_from_config
from vacature_ingestion.models import SourceSpec
from vacature_ingestion.runner import SourceRunResult
from scripts.one_pass_vacancies import (
    _official_page_exclusion, _missing_ranking_evidence,
    RegisterPreflightError, google_free_gate, live_policy, parse_table,
    plan_free_source_batches, run_once, screen_review_candidates, select_free_specs,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {
    "cross_run_deduplication": "TRUE", "max_posting_age_days": "7",
    "max_output_roles": "5", "min_monthly_salary_eur": "3500",
    "min_output_score": "75", "min_core_fit": "40",
    "min_evidence_fit": "10", "allowed_listing_languages": "nl,en",
    "target_role_families": "wordpress_ecosystem,web_design_development,ai_workflow_automation",
    "direct_discovery_order": "ats,discovery_api,job_board,discovery",
    "dedupe_previous_statuses": "seen,shown,submitted,applied,rejected,excluded",
}
def tables():
    return {
        "Config": [{"key": k, "value": v} for k, v in CONFIG.items()],
        "Bronnen": [
            {"source_id": n, "status": "active", "source_type": kind,
             "priority": "high"} for n, kind in [
                ("google-jobs", "discovery"), ("ashby", "ats"),
                ("greenhouse", "ats"), ("lever", "ats"), ("himalayas", "discovery_api"),
                ("remote-ok", "job_board"), ("we-work-remotely", "job_board"),
            ]
        ],
        "Vacatures": [
            {"vacancy_id": "old", "status": "submitted",
             "canonical_url": "https://jobs.ashbyhq.com/acme/old",
             "official_url": "", "title": "WordPress Developer", "employer": "Acme"}
        ],
        "Applications": [{"vacancy_id": "old", "status": "submitted",
                          "application_url": "https://jobs.ashbyhq.com/acme/old"}],
        "Feedback": [{"vacancy_id": "old", "state": "rejected", "applied": "TRUE"}],
        "ApplicationEvents": [{"vacancy_id": "old", "event_type": "submitted"}],
        "CandidateEvidence": [{"evidence_id": "e1", "claim": "WordPress", "active": "TRUE"}],
        "JobSnapshots": [],
    }
def observation(url, title="WordPress Developer", source_type="ats", **kwargs):
    return {"canonical_url": url, "url": url, "title": title,
            "source_type": source_type, "source_id": "ashby",
            "employer": "Acme", **kwargs}

class OnePassTests(unittest.TestCase):
    def test_missing_table_and_columns_fail_closed(self):
        with self.assertRaises(RegisterPreflightError):
            parse_table([], {"vacancy_id"}, "Vacatures")
        with self.assertRaises(RegisterPreflightError):
            parse_table([["wrong"]], {"vacancy_id"}, "Vacatures")

    def test_policy_reads_live_register(self):
        _, p = live_policy(tables())
        self.assertEqual(p.max_posting_age_days, 7)
        self.assertEqual(p.max_output_roles, 5)

    def test_known_applied_and_rejected_role_suppressed(self):
        rows, c = screen_review_candidates([
            observation("https://jobs.ashbyhq.com/acme/old"),
            observation("https://jobs.ashbyhq.com/acme/new", title="AI Automation Engineer"),
        ], tables(), policy_from_config(CONFIG), today=date(2026, 10, 19))
        self.assertEqual(c["previously_registered"], 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "unverified_review_only")
        self.assertNotIn("application_status", rows[0])

    def test_only_configured_history_statuses_are_blocking(self):
        t = tables()
        t["Vacatures"].append({
            "vacancy_id": "unreviewed", "status": "discovered",
            "canonical_url": "https://jobs.ashbyhq.com/acme/unreviewed",
            "official_url": "", "employer": "Other", "title": "Web Developer",
        })
        rows, counts = screen_review_candidates([
            observation("https://jobs.ashbyhq.com/acme/unreviewed",
                        title="Web Developer"),
        ], t, policy_from_config(CONFIG), today=date(2026, 10, 19))
        self.assertEqual(counts["previously_registered"], 0)
        self.assertEqual(len(rows), 1)

    def test_application_history_without_vacancy_row_is_blocked(self):
        t = tables()
        t["Applications"].append({
            "vacancy_id": "orphan", "status": "submitted",
            "application_url": "https://jobs.ashbyhq.com/acme/orphan",
        })
        rows, counts = screen_review_candidates([
            observation("https://jobs.ashbyhq.com/acme/orphan",
                        title="Automation Engineer"),
        ], t, policy_from_config(CONFIG), today=date(2026, 10, 19))
        self.assertEqual(rows, [])
        self.assertEqual(counts["previously_registered"], 1)

    def test_missing_dedupe_config_fails_closed(self):
        t = tables()
        t["Config"] = [r for r in t["Config"] if r["key"] != "dedupe_previous_statuses"]
        with self.assertRaises(RegisterPreflightError):
            screen_review_candidates([], t, policy_from_config(CONFIG),
                                     today=date(2026, 10, 19))

    def test_weak_history_match_is_not_recommended(self):
        rows, c = screen_review_candidates([
            observation("https://jobs.ashbyhq.com/acme/other")
        ], tables(), policy_from_config(CONFIG), today=date(2026, 10, 19))
        self.assertEqual(len(rows), 0)
        self.assertEqual(c["possible_prior_match"], 1)

    def test_hard_mismatches_and_google_unknowns(self):
        items = [
            observation("https://jobs.ashbyhq.com/acme/closed", remote=False),
            observation("https://jobs.ashbyhq.com/acme/oldposting", published_at="2026-08-01"),
            observation("https://jobs.ashbyhq.com/acme/unknown", title="Web Developer",
                        source_type="discovery", remote=None),
        ]
        rows, c = screen_review_candidates(items, tables(), policy_from_config(CONFIG),
                                           today=date(2026, 10, 19))
        self.assertEqual(c["explicit_mismatch"], 2)
        self.assertEqual(len(rows), 1)
        self.assertIn("official_employer_and_exact_open_role", rows[0]["still_to_verify"])

    def test_off_target_search_pages_cannot_crowd_out_ats(self):
        search_rows = [
            {
                "source_id": "google-jobs",
                "source_type": "discovery",
                "canonical_url": "https://example.org/jobs/list-" + str(i),
                "url": "https://example.org/jobs/list-" + str(i),
                "title": "Thousands of unrelated Engineering Jobs",
                "employer": None,
            }
            for i in range(75)
        ]
        official = observation(
            "https://jobs.ashbyhq.com/acme/genuine",
            title="WooCommerce Developer",
            description="Build WordPress features",
        )
        rows, counts = screen_review_candidates(
            search_rows + [official], tables(), policy_from_config(CONFIG),
            today=date(2026, 10, 19), limit=5,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "WooCommerce Developer")
        self.assertEqual(counts["off_target"], 75)
        self.assertEqual(rows[0]["source_types"], ["ats"])

    def test_wordpress_brand_sales_jobs_are_not_web_developer_roles(self):
        items = [
            observation("https://job-boards.greenhouse.io/automatticcareers/jobs/5867610",
                        title="Account Executive, WordPress VIP",
                        source_type="ats"),
            observation("https://job-boards.greenhouse.io/automatticcareers/jobs/8000156",
                        title="Director of Professional Services, WordPress VIP",
                        source_type="ats"),
            observation("https://jobs.ashbyhq.com/acme/real-dev",
                        title="WordPress VIP Plugin Developer",
                        source_type="ats"),
        ]
        rows, counts = screen_review_candidates(
            items, tables(), policy_from_config(CONFIG), today=date(2026, 10, 19),
        )
        self.assertEqual(counts["off_target"], 2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "WordPress VIP Plugin Developer")

    def test_unrelated_ats_titles_do_not_pass_on_company_boilerplate(self):
        noise = [
            observation("https://jobs.ashbyhq.com/acme/account", title="Account Manager",
                        description="We build AI automation and n8n workflows."),
            observation("https://jobs.ashbyhq.com/acme/security", title="Security Engineer",
                        description="Our team builds AI agent tools."),
            observation("https://jobs.ashbyhq.com/acme/talent", title="Talent Community",
                        description="Join our WordPress and WooCommerce company."),
        ]
        rows, counts = screen_review_candidates(
            noise, tables(), policy_from_config(CONFIG), today=date(2026, 10, 19),
        )
        self.assertEqual(rows, [])
        self.assertEqual(counts["off_target"], 3)

    def test_generic_engineering_title_can_be_flagged_from_official_ats_body(self):
        rows, _ = screen_review_candidates([
            observation("https://jobs.ashbyhq.com/acme/swe", title="Software Engineer",
                        description="Build WordPress and WooCommerce plugins.")
        ], tables(), policy_from_config(CONFIG), today=date(2026, 10, 19))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["role_family_hints"], ["wordpress_ecosystem"])
        self.assertEqual(rows[0]["status"], "unverified_review_only")

    def test_source_restricted_himalayas_roles_are_not_eligible_for_nl(self):
        records = [
            {
                "source_id": "himalayas", "source_type": "discovery_api",
                "canonical_url": "https://himalayas.app/companies/velaio/jobs/wp-1",
                "url": "https://himalayas.app/companies/velaio/jobs/wp-1",
                "title": "WordPress senior developer", "employer": "VELAIO",
                "source_metadata": {"location_restriction_names": ["United States"]},
            },
            {
                "source_id": "himalayas", "source_type": "discovery_api",
                "canonical_url": "https://himalayas.app/companies/acme/jobs/wp-2",
                "url": "https://himalayas.app/companies/acme/jobs/wp-2",
                "title": "WordPress developer", "employer": "OtherCo",
                "source_metadata": {"location_restriction_names": ["European Union"]},
            },
        ]
        rows, counts = screen_review_candidates(
            records, tables(), policy_from_config(CONFIG), today=date(2026, 10, 19),
        )
        self.assertEqual(counts["source_location_restricted"], 1)
        self.assertEqual(len(rows), 1)
        self.assertIn("wp-2", rows[0]["official_role_candidate_url"])
        # Aggregator's EU hint still never verifies the employer.
        self.assertEqual(rows[0]["official_checks"]["official_role"], "unverified")

    def test_live_board_country_exclusion_and_stale_discovery_advisory(self):
        t = tables()
        t["Bronnen"].append({
            "source_id": "remotejobs-org", "status": "active",
            "source_type": "discovery_api", "priority": "medium",
        })
        records = [
            {
                "source_id": "remotejobs-org", "source_type": "discovery_api",
                "canonical_url": "https://remotejobs.org/remote-jobs/full-stack-wordpress-developer-outsourcedin",
                "title": "Full-Stack WordPress Developer", "employer": "OutsourcedIn",
                "location": "Philippines", "description": "WordPress development.",
            },
            {
                "source_id": "remotejobs-org", "source_type": "discovery_api",
                "canonical_url": "https://remotejobs.org/remote-jobs/wordpress-developer-elementor-divi-motum",
                "title": "WordPress Developer (Elementor + Divi)", "employer": "Motum",
                "location": "Remote",
                "description": "WE ARE EXCLUSIVELY CONSIDERING APPLICATIONS "
                               "FROM INDIVIDUALS CURRENTLY RESIDING IN LATAM.",
            },
            {
                "source_id": "remote-ok", "source_type": "job_board",
                "canonical_url": "https://remoteok.com/remote-jobs/remote-senior-backend-engineer-build-ai-agents-salesforge-1137114",
                "title": "Senior Backend Engineer Build AI Agents", "employer": "Salesforge",
                "location": "Remote Europe", "published_at": "2026-08-25",
            },
        ]
        candidates, counts = screen_review_candidates(
            records, t, policy_from_config(CONFIG), today=date(2026, 10, 20),
        )
        self.assertEqual(counts["source_location_restricted"], 2)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["employer"], "Salesforge")
        self.assertEqual(candidates[0]["review_alerts"],
                         ["discovery_date_older_than_policy"])
        self.assertEqual(candidates[0]["official_checks"]["official_role"],
                         "unverified")
        self.assertEqual(candidates[0]["status"], "unverified_review_only")

    def test_missing_remote_board_location_never_proves_nl_eligibility(self):
        t = tables()
        candidate = {
            "source_id": "remote-ok", "source_type": "job_board",
            "canonical_url": "https://remoteok.com/remote-jobs/wp-engineer-1234",
            "title": "WordPress Engineer", "employer": "NewCo",
            "location": "Remote", "published_at": None,
        }
        rows, counts = screen_review_candidates(
            [candidate], t, policy_from_config(CONFIG),
            today=date(2026, 10, 20),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["official_checks"]["netherlands"], "unknown")
        self.assertEqual(rows[0]["review_alerts"], [])
        self.assertEqual(counts["source_location_restricted"], 0)

    def test_retired_or_unknown_board_source_never_enters_review_queue(self):
        t = tables()
        row = {
            "source_id": "unapproved-board", "source_type": "job_board",
            "canonical_url": "https://remotejobs.org/remote-jobs/wordpress-developer",
            "title": "WordPress Developer", "employer": "NotApproved",
        }
        results, counts = screen_review_candidates(
            [row], t, policy_from_config(CONFIG), today=date(2026, 10, 20),
        )
        self.assertEqual(results, [])
        self.assertEqual(counts["unapproved_source"], 1)

    def test_official_ats_costa_rica_role_excluded(self):
        rows, counts = screen_review_candidates([
            dict(
                observation(
                    "https://job-boards.greenhouse.io/acquia/jobs/8205142",
                    title="AI Automation Manager", location="Remote - Costa Rica", remote=None,
                    source_metadata={"provider": "greenhouse", "provider_job_id": 8205142},
                ),
                source_id="greenhouse", source_instance="greenhouse:acquia",
                employer="Acquia",
            ),
        ], tables() | {
            "Bronnen": tables()["Bronnen"] + [
                {"source_id": "greenhouse", "status": "active", "source_type": "ats", "priority": "high"}
            ],
        }, policy_from_config(CONFIG), today=date(2026, 10, 19))
        self.assertEqual(rows, [])
        self.assertEqual(counts["official_region_rejected"], 1)

    def test_freelancer_available_post_is_not_a_vacancy(self):
        rows, counts = screen_review_candidates([
            {
                "source_id": "google-jobs", "source_type": "discovery",
                "canonical_url": "https://community.n8n.io/t/available-n8n-ai-engineer/322775",
                "url": "https://community.n8n.io/t/available-n8n-ai-engineer/322775",
                "title": "Available n8n engineer", "employer": None,
            },
        ], tables(), policy_from_config(CONFIG), today=date(2026, 10, 19))
        self.assertEqual(rows, [])
        self.assertEqual(counts["non_job_page"], 1)

    def test_google_snippet_is_not_fit_proof(self):
        rows, counts = screen_review_candidates([
            {
                "source_id": "google-jobs", "source_type": "discovery",
                "canonical_url": "https://example.org/job/strong-identity",
                "url": "https://example.org/job/strong-identity",
                "title": "Unrelated Role",
                "description": "WordPress n8n AI automation",
                "employer": None,
            }
        ], tables(), policy_from_config(CONFIG), today=date(2026, 10, 19))
        self.assertEqual(rows, [])
        self.assertEqual(counts["off_target"], 1)

    def test_official_candidate_gets_evidence_coverage_not_a_score(self):
        t = tables()
        t["CandidateEvidence"] = [{
            "evidence_id": "verified-wp",
            "claim": "Private customer project WordPress and WooCommerce",
            "source_type": "canonical_cv", "active": "TRUE", "confidence": "high",
        }]
        row = observation(
            "https://jobs.ashbyhq.com/acme/clear-wp",
            title="WooCommerce Developer",
            description="Requirements:" + chr(10) + "Experience with WordPress and WooCommerce.",
            source_instance="ashby:acme",
            source_metadata={"provider": "ashby"},
            location="Remote - European Union",
            remote=True,
        )
        rows, _counts = screen_review_candidates(
            [row], t, policy_from_config(CONFIG), today=date(2026, 10, 19),
        )
        self.assertEqual(len(rows), 1)
        review = rows[0]["technical_requirement_review"]
        self.assertEqual(review["status"], "mapped_skills_have_evidence")
        self.assertEqual(review["requirements_with_candidate_evidence"], 2)
        self.assertFalse(review["final_score_authorized"])
        self.assertNotIn("Private customer project", str(rows))

    def test_fake_same_host_different_tenant_not_official_or_matched(self):
        t = tables()
        t["CandidateEvidence"] = [{
            "evidence_id": "verified-wp", "claim": "WordPress",
            "source_type": "canonical_cv", "active": "TRUE", "confidence": "high",
        }]
        row = observation(
            "https://jobs.ashbyhq.com/acme/open",
            title="WordPress Engineer",
            source_instance="ashby:another-company",
            source_metadata={"provider": "ashby"},
            description="Requirements: Experience with WordPress.",
        )
        rows, _ = screen_review_candidates(
            [row], t, policy_from_config(CONFIG), today=date(2026, 10, 19),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["official_checks"]["official_role"], "unverified")
        self.assertEqual(
            rows[0]["technical_requirement_review"]["status"], "requirements_unverified"
        )

    def test_first_party_expired_date_and_old_original_are_excluded(self):
        p = policy_from_config(CONFIG)
        today = date(2026, 10, 19)
        page = {"status": "matching_first_party_jobposting",
                "structured": {"expired_by_valid_through": True,
                               "date_posted": "2026-10-18", "date_posted_valid": True}}
        self.assertEqual(
            _official_page_exclusion(page, p, today), "official_job_expired")
        page["structured"]["expired_by_valid_through"] = False
        page["structured"]["date_posted"] = "2026-09-29"
        self.assertEqual(
            _official_page_exclusion(page, p, today), "official_original_post_too_old")
        page["structured"]["date_posted"] = "2026-10-18"
        self.assertIsNone(_official_page_exclusion(page, p, today))

    def test_only_exact_closed_official_job_is_hard_excluded(self):
        p = policy_from_config(CONFIG)
        today = date(2026, 10, 19)
        self.assertEqual(
            _official_page_exclusion({"status": "closed_at_exact_ats_route"},
                                      p, today), "official_job_route_closed")
        self.assertIsNone(_official_page_exclusion(
            {"status": "unverified", "job_http_status": 0},
            p, today))

    def test_live_readiness_does_not_promote_html_lang_or_skill_tokens(self):
        candidate = {
            "official_checks": {
                "official_role": "confirmed_current_public_ats",
                "remote": "confirmed", "netherlands": "allowed",
            },
            "technical_requirement_review": {
                "status": "mapped_skills_have_evidence",
                "explicit_technical_requirements": 2,
            },
        }
        page = {
            "status": "matching_first_party_jobposting",
            "page_language": "en", "application_page_language": "en",
            "application_language": None, "apply_http_status": 200,
            "structured": {
                "date_posted_valid": True, "date_posted": "2026-10-18",
                "remote_signal": True, "applicant_locations": ["Netherlands"],
            },
        }
        missing = _missing_ranking_evidence(
            candidate, page, policy_from_config(CONFIG),
            date(2026, 10, 19),
        )
        self.assertNotIn("original_publication_date", missing)
        self.assertNotIn("fully_remote_from_first_party", missing)
        self.assertNotIn("netherlands_executable_from_employer", missing)
        self.assertIn("verified_application_form_at_exact_route", missing)
        page["application_form_detected"] = True
        with_form = _missing_ranking_evidence(
            candidate, page, policy_from_config(CONFIG),
            date(2026, 10, 19),
        )
        self.assertNotIn("verified_application_form_at_exact_route", with_form)
        self.assertIn("employer_authorized_application_language", missing)
        self.assertIn("verified_core_duties_and_score_anchors", missing)
        self.assertIn("employer_required_work_languages", missing)

    def test_missing_key_and_quota_fallback(self):
        s = SourceSpec("google-jobs", "discovery", "serpapi_google", "worldwide",
                       options={"queries": ["WordPress remote"]})
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(google_free_gate(s, 1), "not_configured")
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}), patch(
            "scripts.one_pass_vacancies._get_json",
            return_value={"plan_id": "paid"}
        ):
            self.assertEqual(google_free_gate(s, 1), "not_verified_free_or_insufficient_quota")

    def test_free_source_order_follows_live_priority_and_curated_tenants(self):
        t = tables()
        t["Bronnen"] = [
            {"source_id": name, "status": "active", "source_type": kind,
             "priority": "high" if kind == "job_board" else "medium"}
            for name, kind in [
                ("greenhouse", "ats"), ("ashby", "ats"),
                ("remote-ok", "job_board"), ("we-work-remotely", "job_board"),
            ]
        ]
        config = {**CONFIG,
                  "direct_discovery_order": "ats,job_board",
                  "high_source_order": "we-work-remotely,remote-ok"}
        raw = [
            {"source_id": "greenhouse", "source_type": "ats",
             "adapter": "greenhouse", "account": "wordpress-first"},
            {"source_id": "ashby", "source_type": "ats",
             "adapter": "ashby", "account": "alphabetically-first"},
            {"source_id": "remote-ok", "source_type": "job_board",
             "adapter": "remoteok", "account": "global"},
            {"source_id": "we-work-remotely", "source_type": "job_board",
             "adapter": "weworkremotely", "account": "programming"},
        ]
        selected = select_free_specs(raw, t, config, limit=4)
        self.assertEqual(
            [s.instance_id for s in selected],
            ["greenhouse:wordpress-first", "ashby:alphabetically-first",
             "we-work-remotely:programming", "remote-ok:global"],
        )

    def test_free_source_order_cannot_override_register_status(self):
        t = tables()
        t["Bronnen"] = [
            {"source_id": "ashby", "status": "retired", "source_type": "ats",
             "priority": "high"},
            {"source_id": "greenhouse", "status": "active", "source_type": "ats",
             "priority": "medium"},
        ]
        raw = [
            {"source_id": "ashby", "source_type": "ats",
             "adapter": "ashby", "account": "retired"},
            {"source_id": "greenhouse", "source_type": "ats",
             "adapter": "greenhouse", "account": "active"},
        ]
        selected = select_free_specs(raw, t, CONFIG, limit=2)
        self.assertEqual([s.instance_id for s in selected], ["greenhouse:active"])

    def test_existing_ats_and_feeds_preserved(self):
        specs = json.loads((ROOT / "ingestion/source-specs.deploy.json").read_text())
        selected = select_free_specs(specs, tables(), CONFIG, limit=6)
        self.assertTrue(any(s.source_type == "ats" for s in selected))
        self.assertTrue(any(s.source_type in {"discovery_api", "job_board"} for s in selected))
        self.assertTrue(all(s.adapter != "serpapi_google" for s in selected))

    def test_fallback_when_google_blocked_and_no_final_claims(self):
        t = tables()
        class FakeRunner:
            def __init__(self, path): pass
            def close(self): pass
            def run_source(self, source):
                return SourceRunResult(source_instance=source.instance_id,
                    success=True, fetched=1, normalized=1,
                    observations=[observation("https://jobs.ashbyhq.com/acme/unique",
                                              title="AI Automation Engineer")])
        with patch("scripts.one_pass_vacancies.google_free_gate", return_value="not_verified_free_or_insufficient_quota"), \
             patch("scripts.one_pass_vacancies.IngestionRunner", FakeRunner):
            result = run_once(t, ROOT, "page-1", today=date(2026, 10, 19),
                              max_free_sources=3)
        self.assertEqual(result["google"], "not_verified_free_or_insufficient_quota")
        self.assertGreater(result["fallback_sources_successful"], 0)
        self.assertEqual(result["final_recommendations"], [])
        self.assertEqual(result["review_count"], 1)

    def test_all_providers_fail_without_empty_success_claim(self):
        class FailedRunner:
            def __init__(self, path): pass
            def close(self): pass
            def run_source(self, source):
                return SourceRunResult(source_instance=source.instance_id,
                                       success=False, fetched=0, normalized=0)
        with patch("scripts.one_pass_vacancies.google_free_gate", return_value="not_configured"), \
             patch("scripts.one_pass_vacancies.IngestionRunner", FailedRunner):
            with self.assertRaises(RuntimeError):
                run_once(tables(), ROOT, "page-1", max_free_sources=3)

    def test_rotating_deploy_instances_reaches_sources_after_twenty(self):
        specs = json.loads((ROOT / "ingestion/source-specs.deploy.json").read_text())
        t = tables()
        from vacature_ingestion.registry_filter import required_registry_ids
        # ATS tenants are separately gated by employer-specific Register IDs.
        unique = set().union(*(required_registry_ids(spec) for spec in specs))
        t["Bronnen"] = [
            {"source_id": sid, "status": "active", "source_type": "ats",
             "priority": "medium"} for sid in sorted(unique)
        ]
        p0 = plan_free_source_batches(
            specs, t, CONFIG, max_sources=20, round_index=0)
        p1 = plan_free_source_batches(
            specs, t, CONFIG, max_sources=20, round_index=1)
        first = {spec.instance_id for batch in p0 for spec in batch}
        second = {spec.instance_id for batch in p1 for spec in batch}
        self.assertEqual(len(first), 20)
        self.assertEqual(len(second), 20)
        self.assertEqual(len(first | second), len(specs))
        self.assertNotEqual(first, second)
        self.assertTrue(all(len(batch) <= 8 for batch in p0 + p1))

    def test_generated_google_plan_is_bounded_and_reports_discovery_not_scans(self):
        t = tables()
        t["Bronnen"].append({
            "source_id": "company-special", "status": "active",
            "source_type": "employer_direct", "priority": "high",
            "base_url": "https://careers.example.org/openings",
        })
        t["Config"].extend([
            {"key": "target_role_search_terms", "value": "wordpress,woocommerce"},
            {"key": "google_xray_domains",
             "value": "jobs.ashbyhq.com,job-boards.greenhouse.io"},
        ])
        observed = []

        class FakeRunner:
            def __init__(self, path): pass
            def close(self): pass
            def run_source(self, spec):
                observed.append(spec)
                return SourceRunResult(
                    source_instance=spec.instance_id, success=True,
                    fetched=0, normalized=0, observations=[],
                    registry_source_ids=[spec.source_id],
                )

        with patch("scripts.one_pass_vacancies.google_free_gate",
                   return_value="ready"), \
             patch("scripts.one_pass_vacancies.IngestionRunner", FakeRunner), \
             patch("scripts.one_pass_vacancies.evaluate_observations",
                   return_value={"final_recommendations": [], "review_count": 0}):
            result = run_once(
                t, ROOT, "page-1", today=date(2026, 10, 20),
                max_free_sources=3, discovery_round=0, google_queries_per_run=8)
        google = [spec for spec in observed if spec.adapter == "serpapi_google"]
        self.assertEqual(len(google), 1)
        queries = google[0].options["queries"]
        self.assertTrue(any("site:careers.example.org" in q for q in queries))
        self.assertTrue(any("site:jobs.ashbyhq.com" in q for q in queries))
        self.assertLessEqual(len(queries), 8)
        self.assertEqual(google[0].options["max_requests_per_run"], len(queries))
        coverage = result["coverage"]
        self.assertEqual(coverage["google_query_count"], len(queries))
        byid = {item["source_id"]: item for item in coverage["sources"]}
        self.assertEqual(byid["company-special"]["coverage_route"],
                         "google_site_discovery_only")
        self.assertEqual(byid["company-special"]["execution"],
                         "google_batch_succeeded_query_unconfirmed")
        self.assertEqual(byid["google-jobs"]["execution"],
                         "google_provider_batch_succeeded")
        self.assertEqual(result["final_recommendations"], [])

    def test_manual_script_entrypoint_imports_without_network(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/one_pass_vacancies.py"), "--help"],
            cwd=ROOT, capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        self.assertIn("--discovery-round", result.stdout)
        self.assertIn("--google-queries-per-run", result.stdout)

    def test_check_never_fetches_vacancies(self):
        with patch("scripts.one_pass_vacancies.google_free_gate", return_value="ready"), \
             patch("scripts.one_pass_vacancies.IngestionRunner") as runner:
            result = run_once(tables(), ROOT, "check")
        runner.assert_not_called()
        self.assertEqual(result["search_requests"], 0)
        self.assertTrue(result["coverage"]["sources"])
        self.assertEqual(result["coverage"]["execution_counts"].get(
            "direct_attempt_succeeded", 0), 0)

if __name__ == "__main__":
    unittest.main()
