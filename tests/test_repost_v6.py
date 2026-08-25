import unittest

from vacature_engine.policy import LOGIC_VERSION, hard_gate


def good_gate(**overrides):
    data = {
        "posted_age_days": 2,
        "posting_active": True,
        "listing_link_working": True,
        "fully_remote": True,
        "work_eligibility": "allowed",
        "level": "Senior WordPress Developer",
        "central_hard_mismatch_count": 0,
    }
    data.update(overrides)
    return data


class RepostCompatibilityTests(unittest.TestCase):
    def test_logic_version_is_current_v9(self):
        self.assertEqual(LOGIC_VERSION, "2026-08-25-v9")

    def test_explicit_stale_repost_blocks(self):
        result = hard_gate(good_gate(stale_repost=True))
        self.assertFalse(result["pass"])
        self.assertIn("stale_or_recycled_repost", result["reasons"])

    def test_absent_stale_repost_is_backward_compatible(self):
        self.assertTrue(hard_gate(good_gate())["pass"])

    def test_invalid_stale_repost_type_fails_closed(self):
        result = hard_gate(good_gate(stale_repost="true"))
        self.assertFalse(result["pass"])
        self.assertIn("invalid_stale_repost", result["reasons"])


if __name__ == "__main__":
    unittest.main()
