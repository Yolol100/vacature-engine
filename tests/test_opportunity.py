import unittest

from vacature_engine.opportunity import (
    OPPORTUNITY_CONTRACT_VERSION,
    OpportunityAssessment,
    assess_opportunity,
)


class OpportunityAssessmentTests(unittest.TestCase):
    def test_contract_version(self):
        self.assertEqual("1.0", OPPORTUNITY_CONTRACT_VERSION)

    def test_realistic_contract_matrix(self):
        cases = [
            # age, route, applicants, deadline, verified, expected
            (0.5, "employer", 5, 48, True, 100),
            (4, "ats", 20, 120, True, 90),
            (12, "employer", None, None, True, 74),
            (24, "ats", 50, None, True, 77),
            (48, "job_board", 10, 240, True, 71),
            (72, "employer", 100, 336, True, 69),
            (168, "ats", 25, None, True, 66),
            (169, "employer", None, None, True, 53),
            (720, "job_board", 150, None, True, 39),
            (721, "other", None, None, False, 22),
            (None, "employer", None, None, True, 55),
            (None, "ats", 8, 72, True, 71),
        ]
        for age, route, applicants, deadline, verified, expected in cases:
            with self.subTest(age=age, route=route, applicants=applicants):
                result = assess_opportunity(
                    age_hours=age,
                    route_type=route,
                    applicant_count=applicants,
                    deadline_hours=deadline,
                    canonical_verified=verified,
                )
                self.assertIsInstance(result, OpportunityAssessment)
                self.assertEqual(expected, result.score)
                self.assertGreaterEqual(result.score, 0)
                self.assertLessEqual(result.score, 100)

    def test_unknown_signals_are_explicit_warnings(self):
        result = assess_opportunity(
            age_hours=None,
            route_type="employer",
            applicant_count=None,
            deadline_hours=None,
            canonical_verified=True,
        )
        self.assertEqual(
            ("freshness_unknown", "applicant_count_unknown", "deadline_unknown"),
            result.warnings,
        )

    def test_score_does_not_require_candidate_fit_inputs(self):
        result = assess_opportunity(
            age_hours=2,
            route_type="ats",
            applicant_count=12,
            deadline_hours=None,
            canonical_verified=True,
        )
        self.assertEqual(86, result.score)

    def test_rejects_negative_age(self):
        with self.assertRaises(ValueError):
            assess_opportunity(
                age_hours=-1,
                route_type="ats",
                applicant_count=None,
                deadline_hours=None,
                canonical_verified=True,
            )

    def test_rejects_negative_applicant_count(self):
        with self.assertRaises(ValueError):
            assess_opportunity(
                age_hours=1,
                route_type="ats",
                applicant_count=-1,
                deadline_hours=None,
                canonical_verified=True,
            )

    def test_rejects_boolean_applicant_count(self):
        with self.assertRaises(ValueError):
            assess_opportunity(
                age_hours=1,
                route_type="ats",
                applicant_count=True,
                deadline_hours=None,
                canonical_verified=True,
            )

    def test_rejects_negative_deadline(self):
        with self.assertRaises(ValueError):
            assess_opportunity(
                age_hours=1,
                route_type="ats",
                applicant_count=None,
                deadline_hours=-1,
                canonical_verified=True,
            )

    def test_rejects_unknown_route(self):
        with self.assertRaises(ValueError):
            assess_opportunity(
                age_hours=1,
                route_type="aggregator",
                applicant_count=None,
                deadline_hours=None,
                canonical_verified=True,
            )

    def test_requires_boolean_verification(self):
        with self.assertRaises(TypeError):
            assess_opportunity(
                age_hours=1,
                route_type="ats",
                applicant_count=None,
                deadline_hours=None,
                canonical_verified=1,
            )


if __name__ == "__main__":
    unittest.main()
