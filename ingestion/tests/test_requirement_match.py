"""Offline, deterministic privacy and semantic boundary regression coverage."""
import unittest

from vacature_ingestion.requirement_match import compare_requirements
from vacature_ingestion.adapters.ashby import AshbyAdapter
from vacature_ingestion.models import SourceSpec


def row(description, *, source_type="ats", provider="ashby"):
    return {"source_type": source_type, "source_id": "ashby",
            "description": description, "source_metadata": {"provider": provider}}


def proof(claim, *, key="p1", active="TRUE", source="canonical_cv", confidence="high"):
    return {"evidence_id": key, "claim": claim, "active": active,
            "source_type": source, "confidence": confidence}


class RequirementMatchTests(unittest.TestCase):
    def test_mandatory_wordpress_skills_matched(self):
        r = compare_requirements(row(
            "Requirements:\nExperience with WordPress and WooCommerce.\n"
            "Hands-on with PHP and JavaScript.\nBenefits:\nFigma perks available."
        ), [proof("Hands-on with WordPress WooCommerce PHP and JavaScript")])
        self.assertEqual(r["status"], "mapped_skills_have_evidence")
        self.assertEqual(r["explicit_technical_requirements"], 4)
        self.assertEqual(r["requirements_with_candidate_evidence"], 4)
        self.assertFalse(r["final_score_authorized"])

    def test_missing_claim_not_hard_ability_rejection(self):
        r = compare_requirements(row("Requirements:\nExperience with React."), [
            proof("WordPress JavaScript")
        ])
        self.assertEqual(r["status"], "incomplete_requirement_evidence")
        self.assertEqual(r["requirements_without_candidate_evidence"], 1)
        self.assertNotIn("cannot_do", str(r))
        self.assertFalse(r["final_score_authorized"])

    def test_mention_outside_requirement_is_not_skill_requirement(self):
        r = compare_requirements(row(
            "About us:\nWe build WordPress websites.\n"
            "Responsibilities:\nBuild React features for our product."
        ), [proof("WordPress and React")])
        self.assertEqual(r["explicit_technical_requirements"], 0)
        self.assertEqual(r["status"], "requirements_unverified")

    def test_nice_to_have_ignored(self):
        r = compare_requirements(row(
            "Requirements:\nExperience with PHP.\n"
            "Figma is nice to have.\nBonus:\nReact."
        ), [proof("PHP")])
        self.assertEqual(r["explicit_technical_requirements"], 1)
        self.assertEqual(r["requirements_with_candidate_evidence"], 1)

    def test_inactive_or_unverified_candidate_evidence_not_counted(self):
        r = compare_requirements(row("Requirements:\nExperience with PHP."), [
            proof("PHP", active="FALSE"),
            proof("PHP", key="p2", source="web_snippet"),
            proof("PHP", key="p3", confidence="low"),
            proof("PHP", key="p4", confidence="high", source="unverified_blog"),
        ])
        self.assertEqual(r["requirements_with_candidate_evidence"], 0)

    def test_or_alternatives_not_two_mandatory_requirements(self):
        r = compare_requirements(row(
            "Requirements:\nExperience with React or WordPress."
        ), [proof("WordPress")])
        self.assertEqual(r["explicit_technical_requirements"], 0)
        self.assertGreater(r["ambiguous_or_unparsed_requirements"], 0)

    def test_unmapped_alternative_is_unknown_not_wordpress_required(self):
        r = compare_requirements(row("Requirements:\nExperience with Drupal or WordPress."),
                                 [proof("WordPress")])
        self.assertEqual(r["explicit_technical_requirements"], 0)
        self.assertGreater(r["ambiguous_or_unparsed_requirements"], 0)

    def test_unknown_years_and_german_language_block_automatic_fit(self):
        r = compare_requirements(row(
            "Requirements:\n5+ years experience with PHP.\nFluent German is required."
        ), [proof("PHP")])
        self.assertGreater(r["ambiguous_or_unparsed_requirements"], 0)
        self.assertEqual(r["status"], "incomplete_requirement_evidence")

    def test_dutch_explicit_requirement(self):
        r = compare_requirements(row("Vereisten:\nAantoonbare ervaring met WooCommerce."),
                                 [proof("WordPress and WooCommerce")])
        self.assertEqual(r["status"], "mapped_skills_have_evidence")

    def test_substring_does_not_imply_skill(self):
        r = compare_requirements(row("Requirements:\nExperience with Java."),
                                 [proof("JavaScript")])
        self.assertEqual(r["requirements_with_candidate_evidence"], 0)
        self.assertEqual(r["explicit_technical_requirements"], 0)

    def test_no_google_or_board_snippet_can_match_private_evidence(self):
        r = compare_requirements(row(
            "Requirements:\nExperience with WordPress", source_type="discovery"
        ), [proof("WordPress")])
        self.assertEqual(r["status"], "requirements_unverified")
        self.assertEqual(r["requirements_with_candidate_evidence"], 0)

    def test_provider_identity_mismatch_rejected(self):
        r = compare_requirements(row(
            "Requirements:\nExperience with PHP", provider="lever"
        ), [proof("PHP")])
        self.assertEqual(r["status"], "requirements_unverified")

    def test_flattened_ats_sections_keep_required_separate_from_benefits(self):
        raw = (
            "About us: Our company builds React products. "
            "Requirements: Experience with WordPress and WooCommerce. "
            "Benefits: Free JavaScript and PHP training. "
            "Responsibilities: Build React dashboards."
        )
        r = compare_requirements(
            row(raw), [proof("Developed WordPress and WooCommerce stores")]
        )
        self.assertEqual(r["explicit_technical_requirements"], 2)
        self.assertEqual(r["requirements_with_candidate_evidence"], 2)
        self.assertEqual(r["status"], "mapped_skills_have_evidence")
        self.assertFalse(r["final_score_authorized"])

    def test_real_ashby_adapter_normalized_plain_description(self):
        spec = SourceSpec("ashby", "ats", "ashby", "acme")
        record = {
            "id": "42", "title": "WordPress Developer",
            "jobUrl": "https://jobs.ashbyhq.com/acme/42",
            "descriptionPlain": (
                "About us:\\nReact based product company.\\n"
                "Requirements:\\nExperience with PHP and WordPress.\\n"
                "Benefits:\\nFree TypeScript workshops."
            ),
        }
        record["descriptionPlain"] = record["descriptionPlain"].replace("\\\\n", chr(10))
        normalized = AshbyAdapter().normalize_record(
            record, spec, now="2026-10-19T12:00:00Z"
        )
        self.assertIsNotNone(normalized)
        self.assertNotIn(chr(10), normalized["description"])
        report = compare_requirements(
            normalized, [proof("Developed PHP WordPress websites")]
        )
        self.assertEqual(report["explicit_technical_requirements"], 2)
        self.assertEqual(report["requirements_with_candidate_evidence"], 2)

    def test_explicit_non_requirement_does_not_add_mandatory_skill(self):
        r = compare_requirements(
            row("Requirements: PHP experience required. "
                "You do not need React. Nice to have: Figma."),
            [proof("Built PHP projects")]
        )
        self.assertEqual(r["explicit_technical_requirements"], 1)
        self.assertEqual(r["requirements_with_candidate_evidence"], 1)

    def test_negative_candidate_evidence_never_proves_positive_skill(self):
        r = compare_requirements(
            row("Requirements: Experience with React."),
            [proof("No experience with React.", key="negative")]
        )
        self.assertEqual(r["requirements_without_candidate_evidence"], 1)
        self.assertFalse(r["final_score_authorized"])

    def test_unknown_prose_does_not_create_auto_score(self):
        r = compare_requirements(
            row("We have developer requirements that include teamwork and travel. "
                "Our flagship WordPress CMS is used worldwide."),
            [proof("WordPress sites")]
        )
        self.assertEqual(r["explicit_technical_requirements"], 0)
        self.assertEqual(r["status"], "requirements_unverified")

    def test_no_sensitive_evidence_content_in_result(self):
        secret="Private customer project code WordPress"
        r=compare_requirements(row("Requirements:\nExperience with WordPress."),
                               [proof(secret)])
        self.assertNotIn(secret,str(r))
        self.assertNotIn("p1",str(r))
        self.assertEqual(r["requirements_with_candidate_evidence"], 1)


if __name__ == "__main__":
    unittest.main()
