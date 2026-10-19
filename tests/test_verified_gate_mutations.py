"""Exercise each final gate with a scoreable synthetic baseline, without I/O."""
import unittest

from test_verified_ranking_flow import evaluate, fixture


class VerifiedGateMutationTests(unittest.TestCase):
    def test_valid_handoff_reaches_existing_engine_score(self):
        t, row, page, assessment = fixture()
        final = evaluate(t, row, page, assessment)["final_recommendations"]
        self.assertEqual(len(final), 1)
        self.assertEqual(final[0]["score"], 85)

    def test_current_policy_digest_is_required_even_when_new_threshold_is_lower(self):
        t, row, page, assessment = fixture()
        next(item for item in t["Config"] if item["key"] == "min_core_fit")["value"] = "25"
        result = evaluate(t, row, page, assessment)
        self.assertEqual(result["final_recommendations"], [])
        self.assertIn("assessment_inputs_changed", result["review_candidates"][0]["still_to_verify"])

    def test_met_requirement_without_referenced_candidate_proof_never_scores(self):
        t, row, page, assessment = fixture()
        assessment["requirements"][0]["candidate_evidence"] = []
        result = evaluate(t, row, page, assessment)
        self.assertEqual(result["final_recommendations"], [])
        self.assertIn("verified_candidate_requirement_evidence", result["review_candidates"][0]["still_to_verify"])

    def test_unknown_mandatory_requirement_blocks_even_if_no_anchor_uses_it(self):
        t, row, page, assessment = fixture()
        assessment["requirements"][-1]["mandatory"] = True
        result = evaluate(t, row, page, assessment)
        self.assertEqual(result["final_recommendations"], [])
        self.assertIn("mandatory_requirement_unknown", result["review_candidates"][0]["still_to_verify"])

    def test_met_language_requirement_cannot_support_technical_core_anchor(self):
        t, row, page, assessment = fixture()
        assessment["anchors"]["core_fit"]["requirement_ids"] = ["2"]
        result = evaluate(t, row, page, assessment)
        self.assertEqual(result["final_recommendations"], [])
        self.assertIn("verified_anchor:core_fit", result["review_candidates"][0]["still_to_verify"])


if __name__ == "__main__":
    unittest.main()
