"""End-to-end ranking fixtures are synthetic; never live CandidateEvidence."""
import copy
import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from vacature_engine.simple import policy_from_config
from vacature_ingestion.final_review import REVIEW_DIMENSIONS, assessment_context, proof_digest
from vacature_ingestion.official_page import fetch_official_page_evidence
from vacature_ingestion.runner import SourceRunResult
from scripts.one_pass_vacancies import evaluate_observations, run_once
from test_one_pass_vacancies import CONFIG, tables

TODAY = date(2026, 10, 20)
ROOT = Path(__file__).resolve().parents[1]
URL = "https://jobs.ashbyhq.com/fixtureco/role-123"


def fixture():
    t = tables()
    for key in ("Vacatures", "Applications", "Feedback", "ApplicationEvents", "JobSnapshots"):
        t[key] = []
    claims = ["WordPress development and five delivered WordPress projects.",
              "5 years of WordPress development experience.",
              "Fluent English communication.",
              "Works independently in a remote team and documents decisions."]
    t["CandidateEvidence"] = [
        {"evidence_id": "fixture:" + str(i), "claim": claim, "active": "TRUE",
         "source_type": "user_confirmed", "source_ref": "synthetic-fixture",
         "source_locator": "synthetic claim " + str(i), "confidence": "high",
         "verified_at": "2026-10-19"}
        for i, claim in enumerate(claims)
    ]
    description = (
        "Requirements: WordPress development experience. 3 years of WordPress experience. "
        "Fluent English is required. Responsibilities: Build WordPress websites. "
        "Work independently in a remote team. Preferred: WooCommerce projects."
    )
    row = {
        "title": "WordPress Developer", "employer": "FixtureCo", "description": description,
        "canonical_url": URL, "url": URL, "apply_url": URL + "/apply",
        "source_id": "ashby", "source_type": "ats", "source_instance": "ashby:fixtureco",
        "source_metadata": {"provider": "ashby"}, "source_job_id": "role-123",
        "location": "Netherlands", "remote": True, "published_at": "2026-10-19",
    }
    visible = ("WordPress Developer. " + description + " Fully remote role. "
               "Work from the Netherlands. Originally posted on 2026-10-19. "
               "Submit applications in English.")
    schema = {"@type": "JobPosting", "title": row["title"],
              "hiringOrganization": {"name": row["employer"]},
              "datePosted": "2026-10-19", "jobLocationType": "TELECOMMUTE",
              "applicantLocationRequirements": {"name": "Netherlands"}}
    html = ("<html lang='en'><script type='application/ld+json'>" + json.dumps(schema)
            + "</script><body>" + visible + "</body></html>")
    form = ("<html lang='en'><form><input type='email'><input type='file' name='resume'>"
            "<button>Apply</button></form></html>")
    with patch("vacature_ingestion.official_page._fetch_html", side_effect=[(200, html), (200, form)]):
        page = fetch_official_page_evidence(row, active_ids={"ashby"}, today=TODAY)
    config = {r["key"]: r["value"] for r in t["Config"]}
    def reference(i):
        claim = t["CandidateEvidence"][i]
        return {"evidence_id": claim["evidence_id"], "claim_sha256": proof_digest(claim["claim"]),
                "source_ref": claim["source_ref"], "source_status": "verified",
                "source_checked_on": TODAY.isoformat()}
    reqs = [
        ("skills", "WordPress development experience.", 0),
        ("experience", "3 years of WordPress experience.", 1),
        ("languages", "Fluent English is required.", 2),
        ("responsibilities", "Build WordPress websites.", 0),
        ("workstyle", "Work independently in a remote team.", 3),
    ]
    assessment = {
        "schema_version": 1, "reviewer": "vacature-search", "canonical_url": URL,
        "reviewed_on": TODAY.isoformat(), **assessment_context(row, page, config, t["CandidateEvidence"]),
        "employer_verification": {"status": "verified", "checked_on": TODAY.isoformat(),
            "employer_url": "https://fixtureco.example/careers", "official_role_url": URL,
            "ownership_evidence": "Synthetic employer careers page links to this exact ATS role."},
        "facts": {
            "fully_remote": {"value": True, "quote": "Fully remote role."},
            "netherlands_execution": {"value": True, "quote": "Work from the Netherlands."},
            "original_publication": {"value": "2026-10-19", "quote": "Originally posted on 2026-10-19."},
            "application_language": {"value": "en", "quote": "Submit applications in English."},
            "required_languages": {"value": ["en"], "quote": "Fluent English is required."},
        },
        "requirements_complete": True, "reviewed_dimensions": sorted(REVIEW_DIMENSIONS),
        "requirements": [
            {"id": str(i), "kind": kind, "quote": quote, "mandatory": True, "outcome": "met",
             "candidate_evidence": [reference(eid)], "rationale": "Synthetic source supports this specific requirement.",
             **({"language": "en"} if kind == "languages" else {})}
            for i, (kind, quote, eid) in enumerate(reqs)
        ] + [{"id": "optional", "kind": "projects", "quote": "WooCommerce projects.",
              "mandatory": False, "outcome": "unknown", "candidate_evidence": []}],
        "role_families": ["wordpress_ecosystem"],
        "anchors": {
            "core_fit": {"value": 40, "requirement_ids": ["0", "3"], "rationale": "Synthetic strong core fit."},
            "evidence_fit": {"value": 25, "requirement_ids": ["0", "1"], "rationale": "Synthetic direct experience."},
            "workstyle_fit": {"value": 10, "requirement_ids": ["4"], "rationale": "Synthetic matching work style."},
        },
    }
    return t, row, page, assessment


def evaluate(t, row, page, assessment):
    config = {r["key"]: r["value"] for r in t["Config"]}
    return evaluate_observations([row], t, config, policy_from_config(config), today=TODAY,
                                 assessments={URL: assessment} if assessment else {},
                                 page_cache={URL: page})


class VerifiedRankingFlowTests(unittest.TestCase):
    def test_complete_verified_role_uses_existing_engine_and_optional_unknown_is_allowed(self):
        t, row, page, assessment = fixture()
        result = evaluate(t, row, page, assessment)
        self.assertEqual(result["review_count"], 0)
        self.assertEqual(len(result["final_recommendations"]), 1)
        final = result["final_recommendations"][0]
        self.assertEqual(final["score"], 85)
        self.assertEqual(final["score_breakdown"], {"core_fit": 40, "evidence_fit": 25, "workstyle_fit": 10, "recency": 10})
        self.assertIsNone(final["salary_monthly_eur"])
        self.assertNotIn("fixture:0", json.dumps(result))
        self.assertNotIn(t["CandidateEvidence"][0]["claim"], json.dumps(result))

    def test_verified_library_cv_requires_exact_file_id_not_a_fake_link(self):
        t, row, page, assessment = fixture()
        live = t["CandidateEvidence"][0]
        live.update(source_type="library_cv",
                    source_ref="file_" + "0" * 32,
                    source_locator="Experience, page 1")
        for req in assessment["requirements"]:
            for ref in req["candidate_evidence"]:
                if ref["evidence_id"] == live["evidence_id"]:
                    ref["source_ref"] = live["source_ref"]
        config = {r["key"]: r["value"] for r in t["Config"]}
        assessment.update(assessment_context(row, page, config, t["CandidateEvidence"]))
        self.assertEqual(evaluate(t, row, page, assessment)["final_recommendations"][0]["score"], 85)
        live["source_ref"] = "https://example.com/fake-cv"
        for req in assessment["requirements"]:
            for ref in req["candidate_evidence"]:
                if ref["evidence_id"] == live["evidence_id"]:
                    ref["source_ref"] = live["source_ref"]
        assessment.update(assessment_context(row, page, config, t["CandidateEvidence"]))
        self.assertEqual(evaluate(t, row, page, assessment)["final_recommendations"], [])

    def test_no_assessment_never_scores_even_when_technical_tokens_match(self):
        t, row, page, _ = fixture()
        result = evaluate(t, row, page, None)
        self.assertEqual(result["final_recommendations"], [])
        self.assertIn("specialist_evidence_assessment", result["review_candidates"][0]["still_to_verify"])

    def test_unknown_required_language_is_unknown_not_rejected(self):
        t, row, page, a = fixture()
        a["requirements"][2]["outcome"] = "unknown"
        a["requirements"][2]["candidate_evidence"] = []
        a["requirements"][2]["id"] = "private-review-reference"
        result = evaluate(t, row, page, a)
        self.assertEqual(result["final_recommendations"], [])
        self.assertEqual(result["review_count"], 1)
        self.assertEqual(result["official_exclusion_counts"]["verified_mandatory_requirement_mismatch"], 0)
        self.assertNotIn("private-review-reference", json.dumps(result))

    def test_missing_inactive_changed_and_unavailable_candidate_proof_cannot_score(self):
        for change in ("missing", "inactive", "changed", "unavailable", "stale", "no_source"):
            with self.subTest(change=change):
                t, row, page, a = fixture()
                ref = a["requirements"][0]["candidate_evidence"][0]
                if change == "missing": ref["evidence_id"] = "nonexistent"
                if change == "inactive": t["CandidateEvidence"][0]["active"] = "FALSE"
                if change == "changed": t["CandidateEvidence"][0]["claim"] = "Different scope."
                if change == "unavailable": ref["source_status"] = "unavailable"
                if change == "stale": ref["source_checked_on"] = "2026-10-19"
                if change == "no_source": t["CandidateEvidence"][0]["source_ref"] = ""
                self.assertEqual(evaluate(t, row, page, a)["final_recommendations"], [])

    def test_policy_observation_and_page_changes_require_new_assessment(self):
        for change in ("policy", "observation", "page"):
            t, row, page, a = fixture()
            if change == "policy": t["Config"][0]["value"] = "true"
            if change == "observation": row["description"] += " New requirement."
            if change == "page": page["visible_text"] += " Changed."
            result = evaluate(t, row, page, a)
            self.assertEqual(result["final_recommendations"], [])
            self.assertIn("assessment_inputs_changed", result["review_candidates"][0]["still_to_verify"])

    def test_forged_quote_anchor_or_employer_receipt_cannot_score(self):
        for change in ("quote", "anchor", "anchor_reference", "employer", "date", "schema"):
            t, row, page, a = fixture()
            if change == "quote": a["facts"]["fully_remote"]["quote"] = "Invented remote permission."
            if change == "anchor": a["anchors"]["core_fit"]["value"] = 49
            if change == "anchor_reference": a["anchors"]["core_fit"]["requirement_ids"] = ["optional"]
            if change == "employer": a["employer_verification"]["employer_url"] = URL
            if change == "date": a["facts"]["original_publication"]["value"] = "2026-10-20"
            if change == "schema": a["schema_version"] = True
            self.assertEqual(evaluate(t, row, page, a)["final_recommendations"], [])

    def test_stale_closed_non_nl_sales_and_unofficial_roles_never_score(self):
        for change in ("old", "closed", "country", "sales", "unofficial"):
            t, row, page, a = fixture()
            if change == "old": page["structured"]["date_posted"] = "2026-09-01"
            if change == "closed": page["status"] = "closed_at_exact_ats_route"
            if change == "country": row["location"] = "United States only"
            if change == "sales": row["title"] = "Account Executive, WordPress VIP"
            if change == "unofficial": row["source_instance"] = "ashby:imposter"
            self.assertEqual(evaluate(t, row, page, a)["final_recommendations"], [])

    def test_previously_applied_role_never_reaches_final_ranker(self):
        t, row, page, a = fixture()
        t["Applications"] = [{"vacancy_id": "prior", "status": "submitted", "application_url": URL}]
        result = evaluate(t, row, page, a)
        self.assertEqual(result["final_recommendations"], [])
        self.assertEqual(result["preflight_counts"]["previously_registered"], 1)

    def test_duplicate_observations_do_not_create_duplicate_rankings(self):
        t, row, page, a = fixture()
        config = {r["key"]: r["value"] for r in t["Config"]}
        result = evaluate_observations([row, copy.deepcopy(row)], t, config, policy_from_config(config),
                                      today=TODAY, assessments={URL: a}, page_cache={URL: page})
        self.assertEqual(len(result["final_recommendations"]), 1)

    def test_live_thresholds_are_applied_without_changing_weights(self):
        t, row, page, a = fixture()
        next(r for r in t["Config"] if r["key"] == "min_output_score")["value"] = "90"
        config = {r["key"]: r["value"] for r in t["Config"]}
        a.update(assessment_context(row, page, config, t["CandidateEvidence"]))
        result = evaluate(t, row, page, a)
        self.assertEqual(result["final_recommendations"], [])
        self.assertEqual(result["official_exclusion_counts"]["verified_below_live_thresholds"], 1)

    def test_whole_free_run_ranks_without_google_and_does_not_mutate_register(self):
        t, row, page, a = fixture()
        before = copy.deepcopy(t)
        class Runner:
            def __init__(self, path): pass
            def close(self): pass
            def run_source(self, source):
                return SourceRunResult(source.instance_id, success=True, fetched=1,
                                       normalized=1, observations=[row])
        with patch("scripts.one_pass_vacancies.google_free_gate", return_value="not_verified_free_or_insufficient_quota"), \
             patch("scripts.one_pass_vacancies.IngestionRunner", Runner), \
             patch("scripts.one_pass_vacancies.fetch_official_page_evidence", return_value=page) as fetch:
            result = run_once(t, ROOT, "page-1", today=TODAY, max_free_sources=20, verified_assessments=[a])
        self.assertEqual(result["final_recommendations"][0]["score"], 85)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(t, before)

    def test_assessment_in_observation_is_ignored(self):
        t, row, page, a = fixture()
        row["verified_assessment"] = a
        self.assertEqual(evaluate(t, row, page, None)["final_recommendations"], [])

    def test_hidden_form_nonce_changes_do_not_stale_identical_public_evidence(self):
        t, row, page, a = fixture()
        page["job_html_sha256"] = "changed nonce hash"
        page["application_html_sha256"] = "changed CSRF hash"
        self.assertEqual(evaluate(t, row, page, a)["final_recommendations"][0]["score"], 85)

    def test_local_addresses_are_not_independent_public_employer_evidence(self):
        for url in ("https://localhost/private", "https://127.0.0.1/internal", "https://192.168.1.1/admin"):
            t, row, page, a = fixture()
            a["employer_verification"]["employer_url"] = url
            self.assertEqual(evaluate(t, row, page, a)["final_recommendations"], [])

    def test_valid_flag_without_actual_original_date_cannot_score(self):
        for value in (None, "", "invalid-date"):
            t, row, page, a = fixture()
            page["structured"]["date_posted"] = value
            page["structured"]["date_posted_valid"] = True
            a["facts"]["original_publication"]["value"] = value
            config = {r["key"]: r["value"] for r in t["Config"]}
            a.update(assessment_context(row, page, config, t["CandidateEvidence"]))
            self.assertEqual(evaluate(t, row, page, a)["final_recommendations"], [])

    def test_duplicate_or_negative_live_evidence_cannot_support_a_met_requirement(self):
        for change in ("negative", "duplicate_first", "duplicate_last"):
            t, row, page, a = fixture()
            if change == "negative":
                t["CandidateEvidence"][2]["claim"] = "I do not speak English."
                a["requirements"][2]["candidate_evidence"][0]["claim_sha256"] = proof_digest(
                    t["CandidateEvidence"][2]["claim"])
            else:
                duplicate = {**t["CandidateEvidence"][0], "active": "FALSE"}
                t["CandidateEvidence"].insert(0 if change == "duplicate_first" else len(t["CandidateEvidence"]), duplicate)
            config = {r["key"]: r["value"] for r in t["Config"]}
            a.update(assessment_context(row, page, config, t["CandidateEvidence"]))
            self.assertEqual(evaluate(t, row, page, a)["final_recommendations"], [])

    def test_malformed_private_handoff_fails_closed_without_crashing(self):
        mutations = [
            lambda a: a.update(reviewed_dimensions=[{}]),
            lambda a: a["facts"]["application_language"].update(value=[]),
            lambda a: a["requirements"][0].update(kind=[]),
            lambda a: a["requirements"][0].update(outcome=[]),
            lambda a: a["requirements"][0]["candidate_evidence"][0].update(evidence_id=[]),
        ]
        for mutate in mutations:
            t, row, page, a = fixture()
            mutate(a)
            self.assertEqual(evaluate(t, row, page, a)["final_recommendations"], [])

    def test_complete_evidence_timestamp_must_parse_before_ranking(self):
        for verified_at, allowed in (
            ("2026-10-19Tnot-a-timestamp", False),
            ("2026-10-19 not verified", False),
            ("2026-10-19T99:99:99Z", False),
            ("2026-10-19T12:30:00Z", True),
            ("2026-10-19 12:30:00+02:00", True),
        ):
            with self.subTest(verified_at=verified_at):
                t, row, page, a = fixture()
                t["CandidateEvidence"][0]["verified_at"] = verified_at
                config = {r["key"]: r["value"] for r in t["Config"]}
                a.update(assessment_context(row, page, config, t["CandidateEvidence"]))
                self.assertEqual(bool(evaluate(t, row, page, a)["final_recommendations"]), allowed)


if __name__ == "__main__":
    unittest.main()
