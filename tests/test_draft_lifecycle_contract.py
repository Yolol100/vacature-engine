"""Regression checks for caller-owned draft and historical-event boundaries."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DraftLifecycleContractTests(unittest.TestCase):
    def test_outlook_draft_requires_preflight_and_readback(self):
        text = (ROOT / "docs" / "EMAIL-APPLICATION-PACK.md").read_text(encoding="utf-8")
        for marker in ("existing Outlook drafts", "exactly one correct CV", "unsent state", "A draft never means submitted", "draft_created_at"):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_invitation_is_not_interview(self):
        text = (ROOT / "docs" / "MAILBOX-APPLICATION-RECONCILIATION.md").read_text(encoding="utf-8")
        for marker in ("An invitation dated 21 May", "interview_at", "actual interview evidence", "one active verified draft"):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_canonical_cv_and_one_language(self):
        for filename in ("EMAIL-APPLICATION-PACK.md", "FORM-APPLICATION-PACK.md", "APPLICATION-PACK-BEST-PRACTICES.md"):
            text = (ROOT / "docs" / filename).read_text(encoding="utf-8")
            with self.subTest(filename=filename):
                self.assertIn("canonical CV", text)
                self.assertTrue("one language" in text.lower() or "one verified canonical cv" in text.lower())

    def test_engine_remains_mailbox_free(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("does not generate CV or motivation prose", readme)
        self.assertIn("does not infer candidate experience", readme)


if __name__ == "__main__":
    unittest.main()
