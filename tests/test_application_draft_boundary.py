"""Regression checks for caller-owned application draft and lifecycle contracts.

No mailbox calls, private applicant data or automatic submission.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ApplicationDraftBoundaryTests(unittest.TestCase):
    def test_outlook_draft_requires_existing_draft_lookup_and_attachment_readback(self):
        text = (ROOT / "docs" / "EMAIL-APPLICATION-PACK.md").read_text(encoding="utf-8")
        for term in ("existing Outlook drafts", "exactly one correct CV", "unsent", "draft_created_at"):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_mailbox_reconciliation_cannot_mutate_mail(self):
        text = (ROOT / "docs" / "MAILBOX-APPLICATION-RECONCILIATION.md").read_text(encoding="utf-8")
        self.assertIn("read-only", text)
        self.assertIn("invitation", text.lower())
        self.assertIn("not a submission", text)

    def test_cv_language_defaults_match_live_policy(self):
        for filename in ("EMAIL-APPLICATION-PACK.md", "FORM-APPLICATION-PACK.md"):
            with self.subTest(filename=filename):
                text = (ROOT / "docs" / filename).read_text(encoding="utf-8")
                self.assertIn("canonical CV", text)
                self.assertIn("second language", text.lower())
                self.assertIn("CV.docx", text)

    def test_engine_remains_read_only_and_prose_free(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("does not generate CV or motivation prose", readme)
        self.assertIn("GitHub Actions are CI-only", readme)


if __name__ == "__main__":
    unittest.main()
