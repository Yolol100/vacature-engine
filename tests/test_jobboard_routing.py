import unittest

from vacature_engine.policy import LOGIC_VERSION, application_guard, hard_gate


def jobboard_gate():
    return {
        "posted_age_days": 2,
        "posting_active": True,
        "listing_link_working": True,
        "fully_remote": True,
        "netherlands_eligibility": "allowed",
        "level": "Senior WordPress Developer",
        "central_hard_mismatch_count": 0,
    }


def recruitment_draft():
    return {
        "stage": "draft",
        "user_explicitly_requested": True,
        "final_verification_pass": True,
        "hard_gate_pass": True,
        "cv_selected": True,
        "recipient_verified": True,
        "recipient_recruitment_relevant": True,
        "recipient_email": "jobs@example.com",
        "recipient_source_url": "https://example.com/careers",
        "factual_qa": "pass",
        "style_qa": "pass",
        "cv_attachment_ready": True,
        "subject_exact_vacancy_title": True,
    }


class JobboardRoutingTests(unittest.TestCase):
    def test_logic_version_v4(self):
        self.assertEqual(LOGIC_VERSION, "2026-08-25-v4")

    def test_jobboard_listing_keys_pass_without_official_duplicate(self):
        self.assertTrue(hard_gate(jobboard_gate())["pass"])

    def test_legacy_official_gate_keys_remain_compatible(self):
        data = jobboard_gate()
        data["active"] = data.pop("posting_active")
        data["official_link_working"] = data.pop("listing_link_working")
        self.assertTrue(hard_gate(data)["pass"])

    def test_verified_recruitment_email_can_create_draft(self):
        self.assertTrue(application_guard(recruitment_draft())["pass"])

    def test_legacy_role_authorization_remains_compatible(self):
        data = recruitment_draft()
        data["recipient_authorized_for_role"] = data.pop("recipient_recruitment_relevant")
        self.assertTrue(application_guard(data)["pass"])

    def test_no_email_does_not_block_prepare_stage(self):
        data = {
            "stage": "prepare",
            "user_explicitly_requested": True,
            "final_verification_pass": True,
            "hard_gate_pass": True,
            "cv_selected": True,
        }
        self.assertTrue(application_guard(data)["pass"])


if __name__ == "__main__":
    unittest.main()
