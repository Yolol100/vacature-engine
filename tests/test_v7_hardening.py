import unittest

from vacature_engine.policy import LOGIC_VERSION, application_guard, hard_gate


class V9HardeningTests(unittest.TestCase):
    def test_logic_version_v9(self):
        self.assertEqual(LOGIC_VERSION, "2026-08-25-v9")

    def test_any_positive_central_hard_mismatch_blocks(self):
        base = {
            "posted_age_days": 2,
            "posting_active": True,
            "listing_link_working": True,
            "fully_remote": True,
            "work_eligibility": "allowed",
            "level": "Senior Engineer",
            "central_hard_mismatch_count": 0,
        }
        self.assertTrue(hard_gate(base)["pass"])
        for count in (1, 2):
            with self.subTest(count=count):
                data = dict(base)
                data["central_hard_mismatch_count"] = count
                self.assertFalse(hard_gate(data)["pass"])

    def test_final_application_requires_cv_language_ai_authenticity_and_motivation_qa(self):
        data = {
            "stage": "draft",
            "user_explicitly_requested": True,
            "final_verification_pass": True,
            "hard_gate_pass": True,
            "cv_selected": True,
            "work_eligibility_confirmed": True,
            "legitimacy_check_pass": True,
            "application_route": "email",
            "recipient_verified": True,
            "recipient_authorized_for_role": True,
            "recipient_email": "jobs@example.com",
            "recipient_source_url": "https://example.com/jobs/1",
            "factual_qa": "pass",
            "style_qa": "pass",
            "cv_attachment_ready": True,
            "subject_exact_vacancy_title": True,
        }
        self.assertFalse(application_guard(data)["pass"])
        data.update(
            {
                "cv_fit_qa": "pass",
                "letter_language": "en",
                "language_qa": "pass",
                "ai_policy_state": "not_found",
                "ai_policy_compliance": "pass",
                "authenticity_qa": "pass",
                "motivation_qa": "pass",
            }
        )
        self.assertTrue(application_guard(data)["pass"])

    def test_prohibited_ai_policy_cannot_be_overridden_by_legacy_boolean(self):
        data = {
            "stage": "manual",
            "user_explicitly_requested": True,
            "final_verification_pass": True,
            "hard_gate_pass": True,
            "cv_selected": True,
            "work_eligibility_confirmed": True,
            "legitimacy_check_pass": True,
            "application_route": "manual_platform",
            "application_url": "https://example.com/apply",
            "cv_fit_qa": "pass",
            "letter_language": "nl",
            "factual_qa": "pass",
            "style_qa": "pass",
            "language_qa": "pass",
            "ai_policy_state": "prohibited",
            "ai_policy_compliance": "pass",
            "ai_policy_compliant": True,
            "authenticity_qa": "pass",
            "motivation_qa": "pass",
            "cv_upload_ready": True,
        }
        self.assertFalse(application_guard(data)["pass"])


if __name__ == "__main__":
    unittest.main()
