import unittest

from vacature_engine.policy import LOGIC_VERSION, application_guard, hard_gate


class V8HardeningTests(unittest.TestCase):
    def test_logic_version_v8(self):
        self.assertEqual(LOGIC_VERSION, "2026-08-25-v8")

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

    def test_draft_requires_motivation_language_ai_policy_and_authenticity_qa(self):
        data = {
            "stage": "draft",
            "user_explicitly_requested": True,
            "final_verification_pass": True,
            "hard_gate_pass": True,
            "cv_selected": True,
            "work_eligibility_confirmed": True,
            "legitimacy_check_pass": True,
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
        data["motivation_qa_pass"] = True
        self.assertFalse(application_guard(data)["pass"])
        data["language_qa_pass"] = True
        data["ai_policy_compliant"] = True
        data["authenticity_qa_pass"] = True
        self.assertTrue(application_guard(data)["pass"])


if __name__ == "__main__":
    unittest.main()
