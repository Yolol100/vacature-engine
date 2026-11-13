"""Synthetic regression tests for current CV bytes embedded in an unsent .eml."""
import unittest
from email.message import EmailMessage
from vacature_engine.mail_artifacts import verify_unsent_eml_cv

CV = b"synthetic-current-docx-bytes"
OLD = b"synthetic-older-docx-bytes"

def draft(cv=CV, *, filename="CV.docx", to="jobs@example.org", subject="Application", unsent=True, count=1):
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    if unsent:
        msg["X-Unsent"] = "1"
    msg.set_content("Local draft; not sent.")
    for _ in range(count):
        msg.add_attachment(cv, maintype="application", subtype="vnd.openxmlformats-officedocument.wordprocessingml.document", filename=filename)
    return msg.as_bytes()

class MailArtifactTests(unittest.TestCase):
    def check(self, eml, current=CV):
        return verify_unsent_eml_cv(eml, current, expected_filename="CV.docx", expected_recipient="jobs@example.org", expected_subject="Application")

    def test_matching_cv_passes(self):
        self.assertEqual(len(self.check(draft())["sha256"]), 64)

    def test_stale_cv_fails(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            self.check(draft(OLD))

    def test_rebuild_current_cv_passes(self):
        self.check(draft(OLD), OLD)
        self.check(draft(CV), CV)

    def test_wrong_filename_multiple_or_missing_attachment_fails(self):
        for eml in (draft(filename="old.docx"), draft(count=2), draft(count=0)):
            with self.assertRaises(ValueError):
                self.check(eml)

    def test_recipient_subject_and_unsent_flag_fail_closed(self):
        for eml in (draft(to="other@example.org"), draft(subject="Other"), draft(unsent=False)):
            with self.assertRaises(ValueError):
                self.check(eml)

    def test_invalid_inputs_fail(self):
        with self.assertRaises(TypeError):
            self.check("not bytes")
        for name in ("../CV.docx", "folder\\CV.docx"):
            with self.assertRaises(ValueError):
                verify_unsent_eml_cv(draft(), CV, expected_filename=name)
