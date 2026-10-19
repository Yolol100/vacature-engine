"""History joins and scoped vacancy identities stay read-only and fail narrowly."""
from copy import deepcopy
from datetime import date
import unittest
from unittest.mock import patch

from scripts.one_pass_vacancies import evaluate_observations, screen_review_candidates
from vacature_engine.simple import policy_from_config


CONFIG = {
    "cross_run_deduplication": "TRUE", "max_posting_age_days": "7",
    "max_output_roles": "5", "min_monthly_salary_eur": "3500",
    "min_output_score": "75", "min_core_fit": "40", "min_evidence_fit": "10",
    "allowed_listing_languages": "nl,en",
    "target_role_families": "wordpress_ecosystem,web_design_development,ai_workflow_automation",
    "direct_discovery_order": "ats,discovery_api,job_board,discovery",
    "dedupe_previous_statuses": "seen,shown,submitted,applied,rejected,interview,offer,excluded",
    "application_event_types": "submitted,employer_reply,interview,offer,rejected",
    "application_legacy_status_aliases": "applied=submitted",
    "nonproduction_vacancy_id_prefixes": "test:,history:",
    "nonproduction_records_excluded_from_search_and_metrics": "TRUE",
}
TODAY = date(2026, 10, 20)


def tables():
    return {
        "Config": [{"key": key, "value": value} for key, value in CONFIG.items()],
        "Bronnen": [{"source_id": provider, "source_type": kind,
                     "status": "active", "priority": "high"}
                    for provider, kind in (("ashby", "ats"), ("greenhouse", "ats"),
                                           ("remote-ok", "job_board"))],
        "Vacatures": [], "Applications": [], "ApplicationEvents": [],
        "Feedback": [], "JobSnapshots": [], "CandidateEvidence": [],
    }


def observation(url="https://jobs.ashbyhq.com/acme/current", **extra):
    return {"source_id": "ashby", "source_type": "ats",
            "canonical_url": url, "url": url, "title": "WordPress Developer",
            "employer": "Acme", **extra}


def vacancy(vacancy_id="recorded", url="https://jobs.ashbyhq.com/acme/current",
            status="discovered", **extra):
    return {"vacancy_id": vacancy_id, "status": status, "canonical_url": url,
            "official_url": "", "title": "Older title", "employer": "Old name", **extra}


def screen(rows, register):
    return screen_review_candidates(rows, register, policy_from_config(CONFIG), today=TODAY)


class HistoryReviewTests(unittest.TestCase):
    def test_feedback_state_overrides_stale_discovered_anchor_for_dedupe(self):
        register = tables()
        register["Vacatures"] = [vacancy()]
        register["Feedback"] = [{"vacancy_id": "recorded", "state": "rejected", "applied": "FALSE"}]
        rows, counts = screen([observation()], register)
        self.assertEqual(rows, [])
        self.assertEqual(counts["previously_registered"], 1)

    def test_feedback_applied_flag_joins_anchor_without_state(self):
        register = tables()
        register["Vacatures"] = [vacancy()]
        register["Feedback"] = [{"vacancy_id": "recorded", "state": "", "applied": "TRUE"}]
        self.assertEqual(screen([observation()], register)[1]["previously_registered"], 1)

    def test_application_events_join_stale_anchor_and_recognize_reply(self):
        for event in ({"event_type": "submitted"}, {"event_type": "employer_reply"},
                      {"event_type": "legacy_event", "status_after": "applied"}):
            with self.subTest(event=event):
                register = tables()
                register["Vacatures"] = [vacancy()]
                register["ApplicationEvents"] = [{"vacancy_id": "recorded", **event}]
                self.assertEqual(screen([observation()], register)[1]["previously_registered"], 1)

    def test_unknown_event_does_not_invent_reviewed_status(self):
        register = tables()
        register["Vacatures"] = [vacancy()]
        register["ApplicationEvents"] = [{"vacancy_id": "recorded", "event_type": "source_imported"}]
        rows, counts = screen([observation()], register)
        self.assertEqual(len(rows), 1)
        self.assertEqual(counts["previously_registered"], 0)

    def test_snapshots_inherit_feedback_history_but_not_discovery_alone(self):
        register = tables()
        register["Vacatures"] = [vacancy(url="https://example.com/jobs/new-route")]
        register["JobSnapshots"] = [{"vacancy_id": "recorded",
                                      "canonical_url": "https://jobs.ashbyhq.com/acme/current"}]
        self.assertEqual(len(screen([observation()], register)[0]), 1)
        register["Feedback"] = [{"vacancy_id": "recorded", "state": "applied"}]
        self.assertEqual(screen([observation()], register)[1]["previously_registered"], 1)

    def test_orphan_application_apply_route_blocks_corresponding_exact_role(self):
        register = tables()
        register["Applications"] = [{
            "vacancy_id": "orphan", "status": "submitted",
            "application_url": "https://jobs.ashbyhq.com/acme/current/application",
        }]
        rows, counts = screen([observation()], register)
        self.assertEqual(rows, [])
        self.assertEqual(counts["previously_registered"], 1)

    def test_unknown_ats_route_shape_retains_exact_recorded_application_url(self):
        register = tables()
        url = "https://boards.greenhouse.io/embed/job_app?for=acme&token=12345"
        register["Applications"] = [{"vacancy_id": "prior", "status": "submitted",
                                      "application_url": url}]
        rows, counts = screen([observation(url, source_id="greenhouse")], register)
        self.assertEqual(rows, [])
        self.assertEqual(counts["previously_registered"], 1)

    def test_greenhouse_host_migration_matches_provider_tenant_and_job(self):
        register = tables()
        register["Vacatures"] = [vacancy(
            status="submitted", url="https://boards.greenhouse.io/acme/jobs/123?utm_source=old",
        )]
        item = observation("https://job-boards.greenhouse.io/acme/jobs/123",
                           source_id="greenhouse", source_instance="greenhouse:acme",
                           title="WooCommerce Engineer")
        self.assertEqual(screen([item], register)[1]["previously_registered"], 1)

    def test_explicit_scoped_provider_id_survives_changed_custom_url(self):
        register = tables()
        register["Vacatures"] = [vacancy(
            status="seen", url="https://acme.example.com/careers/old-name",
            source_id="ashby", source_job_id="acme:123",
        )]
        item = observation("https://acme.example.com/careers/new-name",
                           source_job_id="123", source_instance="ashby:acme")
        self.assertEqual(screen([item], register)[1]["previously_registered"], 1)

    def test_same_provider_job_number_does_not_merge_distinct_tenants(self):
        items = [observation("https://jobs.ashbyhq.com/first/123", employer="First",
                             source_job_id="123", source_instance="ashby:first"),
                 observation("https://jobs.ashbyhq.com/second/123", employer="Second",
                             source_job_id="123", source_instance="ashby:second")]
        register = tables()
        self.assertEqual(len(screen(items, register)[0]), 2)
        register["Vacatures"] = [vacancy(
            status="seen", url=items[0]["canonical_url"], source_id="ashby",
            source_job_id="first:123", employer="First", title="Old title",
        )]
        rows, counts = screen(items, register)
        self.assertEqual([row["employer"] for row in rows], ["Second"])
        self.assertEqual(counts["previously_registered"], 1)

    def test_unscoped_opaque_ids_cannot_merge_jobs_from_unknown_tenants(self):
        items = [observation("https://first.example.com/jobs/123", source_job_id="123", employer="First"),
                 observation("https://second.example.com/jobs/123", source_job_id="123", employer="Second")]
        self.assertEqual(len(screen(items, tables())[0]), 2)

    def test_conflicting_declared_tenant_does_not_match_other_employers_history(self):
        register = tables()
        register["Vacatures"] = [vacancy(status="seen", url="https://jobs.ashbyhq.com/first/123")]
        item = observation("https://jobs.ashbyhq.com/second/123", employer="Second",
                           source_instance="ashby:second", source_job_id="first:123")
        rows, counts = screen([item], register)
        self.assertEqual(len(rows), 1)
        self.assertEqual(counts["previously_registered"], 0)

    def test_nonproduction_history_never_suppresses_production_role(self):
        register = tables()
        url = observation()["canonical_url"]
        register["Vacatures"] = [vacancy("test:recorded", status="seen")]
        register["Applications"] = [{"vacancy_id": "history:app", "status": "submitted",
                                      "application_url": url}]
        register["Feedback"] = [{"vacancy_id": "test:feedback", "state": "rejected",
                                  "canonical_url": url}]
        register["ApplicationEvents"] = [{"vacancy_id": "test:event", "event_type": "submitted",
                                           "canonical_url": url}]
        register["JobSnapshots"] = [{"vacancy_id": "test:recorded", "canonical_url": url}]
        rows, counts = screen([observation()], register)
        self.assertEqual(len(rows), 1)
        self.assertEqual(counts["previously_registered"], 0)

    def test_nonproduction_observation_is_removed_before_clustering(self):
        production = observation()
        test_row = {**production, "vacancy_id": "test:sample", "title": "Account Executive"}
        rows, counts = screen([test_row, production], tables())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "WordPress Developer")
        self.assertEqual(counts["nonproduction"], 1)

    def test_retired_observation_cannot_displace_approved_source_in_cluster(self):
        register = tables()
        register["Bronnen"] = [row for row in register["Bronnen"] if row["source_id"] != "ashby"]
        items = [observation(), observation(source_id="remote-ok", source_type="job_board")]
        rows, counts = screen(items, register)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_types"], ["job_board"])
        self.assertEqual(counts["unapproved_source"], 1)

    def test_direct_vacancy_id_matches_event_history_without_url(self):
        register = tables()
        register["ApplicationEvents"] = [{"vacancy_id": "recorded", "event_type": "submitted"}]
        rows, counts = screen([observation(vacancy_id="recorded")], register)
        self.assertEqual(rows, [])
        self.assertEqual(counts["previously_registered"], 1)

    def test_weak_match_is_pending_without_merge_or_status_mutation(self):
        register = tables()
        register["Vacatures"] = [vacancy(status="seen", title="WordPress Developer",
                                         employer="Acme", url="https://jobs.ashbyhq.com/acme/other")]
        items = [observation()]
        before_register, before_items = deepcopy(register), deepcopy(items)
        rows, counts = screen(items, register)
        self.assertEqual(rows, [])
        self.assertEqual(counts["possible_prior_match"], 1)
        self.assertEqual(counts["previously_registered"], 0)
        self.assertEqual(register, before_register)
        self.assertEqual(items, before_items)

    def test_requirement_dimensions_are_only_compared_for_verified_ats(self):
        item = observation(source_instance="ashby:acme", source_metadata={"provider": "ashby"},
                           description="Requirements:\nWordPress experience required.")
        rows, _ = screen([item], tables())
        self.assertNotEqual(rows[0]["requirement_dimensions"]["status"], "requirements_unverified")
        item["source_instance"] = "ashby:other"
        rows, _ = screen([item], tables())
        self.assertEqual(rows[0]["requirement_dimensions"]["status"], "requirements_unverified")
        self.assertFalse(rows[0]["requirement_dimensions"]["final_score_authorized"])

    def test_custom_employer_ats_url_does_not_hide_explicit_us_location(self):
        item = observation(
            "https://employer.example.com/careers/wordpress-developer?gh_jid=1234",
            source_id="greenhouse", source_instance="greenhouse:custom-employer",
            source_metadata={"provider": "greenhouse"},
            remote=True, location="United States (Remote)",
        )
        register = tables()
        before_register, before_item = deepcopy(register), deepcopy(item)
        rows, counts = screen([item], register)
        self.assertEqual(rows, [])
        self.assertEqual(counts["source_location_restricted"], 1)
        self.assertEqual(counts["official_region_rejected"], 0)
        self.assertEqual(register, before_register)
        self.assertEqual(item, before_item)

    def test_positive_custom_ats_location_never_verifies_official_role_or_nl(self):
        for location in ("Remote", "European Union", "Netherlands"):
            with self.subTest(location=location):
                item = observation(
                    "https://employer.example.com/careers/wordpress-developer?gh_jid=1234",
                    source_id="greenhouse", source_instance="greenhouse:custom-employer",
                    source_metadata={"provider": "greenhouse"}, remote=True,
                    location=location,
                )
                rows, counts = screen([item], tables())
                self.assertEqual(len(rows), 1)
                self.assertEqual(counts["source_location_restricted"], 0)
                self.assertEqual(rows[0]["official_checks"]["official_role"], "unverified")
                self.assertEqual(rows[0]["official_checks"]["netherlands"], "unknown")
                self.assertEqual(rows[0]["status"], "unverified_review_only")

    def test_custom_ats_explicit_foreign_residency_uses_same_negative_gate(self):
        item = observation(
            "https://employer.example.com/careers/wordpress-developer?gh_jid=1234",
            source_id="greenhouse", source_instance="greenhouse:custom-employer",
            source_metadata={"provider": "greenhouse"}, location="Remote",
            description="Applicants must be based in the United States.",
        )
        rows, counts = screen([item], tables())
        self.assertEqual(rows, [])
        self.assertEqual(counts["source_location_restricted"], 1)

    def test_custom_ats_office_boilerplate_is_not_a_residency_restriction(self):
        item = observation(
            "https://employer.example.com/careers/wordpress-developer?gh_jid=1234",
            source_id="greenhouse", source_instance="greenhouse:custom-employer",
            source_metadata={"provider": "greenhouse"}, location="Remote",
            description="Our office is in the United States. We build WordPress sites.",
        )
        rows, counts = screen([item], tables())
        self.assertEqual(len(rows), 1)
        self.assertEqual(counts["source_location_restricted"], 0)
        self.assertEqual(rows[0]["official_checks"]["official_role"], "unverified")

    def test_official_page_originals_keep_the_same_tenant_scope_as_screening(self):
        items = [
            observation("https://jobs.ashbyhq.com/first/123", employer="First",
                        source_job_id="123", source_instance="ashby:first",
                        source_metadata={"provider": "ashby"}),
            observation("https://jobs.ashbyhq.com/second/123", employer="Second",
                        source_job_id="123", source_instance="ashby:second",
                        source_metadata={"provider": "ashby"}),
        ]
        page = {"status": "unverified", "page_language": None,
                "application_language": None, "structured": None}
        with patch("scripts.one_pass_vacancies.fetch_official_page_evidence", return_value=page) as fetch:
            result = evaluate_observations(
                items, tables(), CONFIG, policy_from_config(CONFIG), today=TODAY,
                assessments={}, page_cache={},
            )
        self.assertEqual(len(result["review_candidates"]), 2)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual({call.args[0]["source_instance"] for call in fetch.call_args_list},
                         {"ashby:first", "ashby:second"})
        self.assertTrue(all(call.args[0]["source_job_id"] == "123"
                            for call in fetch.call_args_list))

    def test_nonproduction_original_cannot_contaminate_official_page_evidence(self):
        item = observation(source_job_id="123", source_instance="ashby:acme",
                           source_metadata={"provider": "ashby"})
        test_row = {**item, "vacancy_id": "test:sample", "source_job_id": "different",
                    "published_at": "2026-10-20", "description": "Discarded test data"}
        page = {"status": "unverified", "page_language": None,
                "application_language": None, "structured": None}
        before = deepcopy([item, test_row])
        with patch("scripts.one_pass_vacancies.fetch_official_page_evidence", return_value=page) as fetch:
            result = evaluate_observations(
                [item, test_row], tables(), CONFIG, policy_from_config(CONFIG), today=TODAY,
                assessments={}, page_cache={},
            )
        self.assertEqual(result["preflight_counts"]["nonproduction"], 1)
        fetch.assert_called_once()
        original = fetch.call_args.args[0]
        self.assertIsNone(original.get("vacancy_id"))
        self.assertNotEqual(original.get("description"), "Discarded test data")
        self.assertEqual([item, test_row], before)


if __name__ == "__main__":
    unittest.main()
