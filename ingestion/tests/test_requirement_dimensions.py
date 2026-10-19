"""Literal review coverage must never become invented suitability or a score."""
import json
import unittest

from vacature_ingestion.requirement_match import (
    compare_requirement_dimensions, compare_requirements,
)


def official(description):
    return {"source_type": "ats", "source_id": "ashby", "description": description,
            "source_metadata": {"provider": "ashby"}}


def evidence(claim, **changes):
    return {"evidence_id": "private-fixture-proof", "claim": claim,
            "active": "TRUE", "confidence": "high", "source_type": "canonical_cv",
            "source_ref": "fixture://verified-cv", "source_locator": "Experience",
            "verified_at": "2026-10-19T12:00:00Z", **changes}


def review(description, claims):
    return compare_requirement_dimensions(official(description), claims)


class RequirementDimensionTests(unittest.TestCase):
    def test_mandatory_and_optional_skills_are_separate_review_evidence(self):
        report = review("Requirements: Experience with WordPress and PHP. "
                        "Preferred qualifications: Experience with React. "
                        "Benefits: Free Python training.",
                        [evidence("Developed WordPress PHP websites.")])
        dimensions = report["dimensions"]
        self.assertEqual({r["skill"] for r in dimensions["mandatory_skills"]},
                         {"wordpress", "php"})
        self.assertEqual(dimensions["optional_skills"],
                         [{"skill": "react", "candidate_evidence": "unknown"}])
        self.assertTrue(all(r["candidate_evidence"] == "present"
                            for r in dimensions["mandatory_skills"]))
        self.assertTrue(report["semantic_review_required"])
        self.assertFalse(report["final_score_authorized"])

    def test_missing_skills_are_unknown_and_never_ability_rejections(self):
        report = review("Requirements: Experience with PHP.", [evidence("WordPress")])
        self.assertEqual(report["dimensions"]["mandatory_skills"][0]["candidate_evidence"], "unknown")
        self.assertNotIn("rejected", json.dumps(report))
        self.assertNotIn("ineligible", json.dumps(report))

    def test_new_dimensions_require_traceable_verified_sources(self):
        for key in ("verified_at", "source_ref", "source_locator"):
            with self.subTest(missing=key):
                claim = evidence("PHP")
                del claim[key]
                report = review("Requirements: Experience with PHP.", [claim])
                self.assertEqual(report["dimensions"]["mandatory_skills"][0]["candidate_evidence"], "unknown")
        report = review("Requirements: Experience with PHP.",
                        [evidence("PHP", verified_at="verified by someone")])
        self.assertEqual(report["dimensions"]["mandatory_skills"][0]["candidate_evidence"], "unknown")

    def test_existing_aggregate_contract_remains_compatible(self):
        claim = {"claim": "PHP", "active": "TRUE", "confidence": "high",
                 "source_type": "canonical_cv", "evidence_id": "legacy-proof"}
        result = compare_requirements(official("Requirements: Experience with PHP."), [claim])
        self.assertEqual(result["status"], "mapped_skills_have_evidence")
        self.assertEqual(result["requirements_with_candidate_evidence"], 1)
        self.assertNotIn("dimensions", result)

    def test_unapproved_inactive_low_confidence_and_negative_claims_do_not_match(self):
        claims = [evidence("PHP", active="FALSE"), evidence("PHP", confidence="low"),
                  evidence("PHP", source_type="web_snippet"),
                  evidence("No experience with PHP."), evidence("Learning PHP.")]
        report = review("Requirements: Experience with PHP.", claims)
        self.assertEqual(report["dimensions"]["mandatory_skills"][0]["candidate_evidence"], "unknown")

    def test_years_match_only_the_same_explicit_skill_scope(self):
        report = review("Requirements: 5+ years of experience with PHP.",
                        [evidence("10 years of experience with WordPress. "
                                  "2 years of experience with PHP.")])
        requirement = report["dimensions"]["experience_years"][0]
        self.assertEqual(requirement["skills"], ["php"])
        self.assertEqual(requirement["minimum_years"], 5)
        self.assertEqual(requirement["candidate_evidence"], "unknown")
        result = review("Requirements: 5+ years of experience with PHP.",
                        [evidence("6 years of PHP experience.")])
        self.assertEqual(result["dimensions"]["experience_years"][0]["candidate_evidence"], "present")

    def test_overlapping_experience_claims_are_never_added_together(self):
        report = review("Requirements: 5 years of experience with PHP.",
                        [evidence("3 years of experience with PHP.", evidence_id="one"),
                         evidence("3 years of experience with PHP.", evidence_id="two")])
        self.assertEqual(report["dimensions"]["experience_years"][0]["candidate_evidence"], "unknown")

    def test_mixed_or_unscoped_years_need_interpretation(self):
        report = review("Requirements: 5 years of experience with PHP and WordPress.",
                        [evidence("10 years of experience with PHP.")])
        self.assertEqual(report["dimensions"]["experience_years"], [])
        self.assertGreater(report["ambiguous_or_unparsed_requirements"], 0)
        result = review("Requirements: 3 years of experience with PHP.",
                        [evidence("10 years of professional experience. Recently learned PHP.")])
        self.assertEqual(result["dimensions"]["experience_years"][0]["candidate_evidence"], "unknown")

    def test_language_proficiency_does_not_transfer_between_languages(self):
        report = review("Requirements: Fluent German. Fluent English.",
                        [evidence("I speak German at A1. Fluent English.")])
        languages = {r["language"]: r for r in report["dimensions"]["languages"]}
        self.assertEqual(languages["de"]["candidate_evidence"], "unknown")
        self.assertEqual(languages["en"]["candidate_evidence"], "present")
        report = review("Requirements: Fluent German.",
                        [evidence("Not fluent German.")])
        self.assertEqual(report["dimensions"]["languages"][0]["candidate_evidence"], "unknown")

    def test_cefr_comparison_requires_an_explicit_cefr_claim(self):
        requirement = "Requirements: English C1."
        positive = review(requirement, [evidence("English C2.")])
        unknown = review(requirement, [evidence("Fluent English.")])
        self.assertEqual(positive["dimensions"]["languages"][0]["candidate_evidence"], "present")
        self.assertEqual(unknown["dimensions"]["languages"][0]["candidate_evidence"], "unknown")

    def test_negated_ability_and_zero_project_claims_never_become_positive(self):
        language = review("Requirements: English communication required.",
                          [evidence("I do not speak English.")])
        self.assertEqual(language["dimensions"]["languages"][0]["candidate_evidence"], "unknown")
        for claim in ("No WordPress projects delivered.", "Developed 0 WordPress projects."):
            with self.subTest(claim=claim):
                project = review("Requirements: Portfolio of WordPress projects.", [evidence(claim)])
                self.assertEqual(project["dimensions"]["projects"][0]["candidate_evidence"], "unknown")

    def test_shared_language_level_remains_unparsed(self):
        result = review("Requirements: Fluent English and German.",
                        [evidence("Fluent English. I speak German.")])
        self.assertEqual({r["candidate_evidence"] for r in result["dimensions"]["languages"]}, {"unknown"})
        self.assertGreater(result["ambiguous_or_unparsed_requirements"], 0)

    def test_responsibilities_require_literal_action_and_skill_evidence(self):
        report = review("About us: We build React products. "
                        "Responsibilities: Maintain WordPress websites. Build PHP integrations.",
                        [evidence("Maintained WordPress websites. Familiar with PHP.")])
        duties = {r["action"]: r for r in report["dimensions"]["responsibilities"]}
        self.assertEqual(duties["maintain"]["candidate_evidence"], "present")
        self.assertEqual(duties["develop"]["candidate_evidence"], "unknown")
        self.assertEqual(report["dimensions"]["mandatory_skills"], [])

    def test_work_style_does_not_confuse_async_code_with_async_collaboration(self):
        report = review("Work style: Asynchronous collaboration. Work independently.",
                        [evidence("Built asynchronous JavaScript features. I work independently.")])
        styles = {r["style"]: r for r in report["dimensions"]["work_style"]}
        self.assertEqual(styles["asynchronous_collaboration"]["candidate_evidence"], "unknown")
        self.assertEqual(styles["independent_work"]["candidate_evidence"], "present")

    def test_responsibility_actions_do_not_transfer_to_another_technology(self):
        report = review("Responsibilities: Build React features.",
                        [evidence("Built WordPress websites and maintained React features.")])
        self.assertEqual(report["dimensions"]["responsibilities"][0]["candidate_evidence"], "unknown")

    def test_projects_require_completed_work_not_an_index_or_profile_link(self):
        requirement = "Requirements: Portfolio of WordPress projects."
        index = review(requirement, [evidence("WordPress portfolio index.")])
        real = review(requirement, [evidence("Developed and delivered WordPress websites.")])
        self.assertEqual(index["dimensions"]["projects"][0]["candidate_evidence"], "unknown")
        self.assertEqual(real["dimensions"]["projects"][0]["candidate_evidence"], "present")
        count = review("Requirements: Portfolio of 3 WordPress projects.",
                       [evidence("Developed a WordPress website.")])
        self.assertEqual(count["dimensions"]["projects"][0]["candidate_evidence"], "unknown")

    def test_alternatives_nonrequirements_and_unmapped_conditions_are_not_guessed(self):
        report = review("Requirements: Experience with WordPress or Drupal. "
                        "React is not required. Must have a professional certificate.",
                        [evidence("WordPress React")])
        self.assertEqual(report["dimensions"]["mandatory_skills"], [])
        self.assertGreaterEqual(report["ambiguous_or_unparsed_requirements"], 2)

    def test_board_descriptions_cannot_claim_official_requirement_evidence(self):
        row = official("Requirements: Experience with PHP.")
        row["source_type"] = "job_board"
        result = compare_requirement_dimensions(row, [evidence("PHP")])
        self.assertEqual(result["status"], "requirements_unverified")
        self.assertFalse(any(result["dimensions"].values()))

    def test_private_candidate_claims_references_and_durations_are_not_exported(self):
        claim = evidence("Private customer name: 19 years of experience with PHP.")
        report = review("Requirements: 3 years of experience with PHP.", [claim])
        public = json.dumps(report)
        for private in (claim["claim"], claim["evidence_id"], claim["source_ref"],
                        claim["source_locator"], claim["verified_at"], "19"):
            self.assertNotIn(private, public)

    def test_malformed_claim_rows_fail_closed(self):
        report = review("Requirements: Experience with PHP.",
                        [None, [], evidence("PHP", source_type=[]), evidence("PHP", evidence_id=[])])
        self.assertEqual(report["dimensions"]["mandatory_skills"][0]["candidate_evidence"], "unknown")


if __name__ == "__main__":
    unittest.main()
