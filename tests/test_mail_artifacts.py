"""Synthetic regression tests for current CV bytes embedded in an unsent .eml."""
import base64
import unittest
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
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

    def test_recipient_set_rejects_extra_to_and_hidden_recipients(self):
        self.check(draft(to="Hiring <JOBS@example.org>"))
        for bad in ("jobs@example.org, other@example.org", "other@example.org"):
            with self.subTest(to=bad), self.assertRaisesRegex(ValueError, "recipient"):
                self.check(draft(to=bad))
        for header in ("Cc", "Bcc", "Resent-To", "Resent-Cc", "Resent-Bcc"):
            msg = BytesParser(policy=policy.default).parsebytes(draft())
            msg[header] = "other@example.org"
            with self.subTest(header=header), self.assertRaisesRegex(ValueError, "recipient"):
                self.check(msg.as_bytes())

    def test_duplicate_recipient_and_subject_headers_are_rejected(self):
        msg = draft()
        self.assertIn(b"Subject: Application\n", msg)
        duplicated = msg.replace(
            b"Subject: Application\n",
            b"Subject: Application\nSubject: Changed\n",
            1,
        )
        with self.assertRaisesRegex(ValueError, "duplicate email subject"):
            self.check(duplicated)
        doubled_to = msg.replace(
            b"To: jobs@example.org\n",
            b"To: jobs@example.org\nTo: other@example.org\n",
            1,
        )
        with self.assertRaisesRegex(ValueError, "recipient"):
            self.check(doubled_to)

    def test_docx_mime_duplicate_with_wrong_extension_is_rejected(self):
        msg = BytesParser(policy=policy.default).parsebytes(draft())
        msg.add_attachment(
            OLD, maintype="application",
            subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="old.txt",
        )
        with self.assertRaisesRegex(ValueError, "exactly one DOCX"):
            self.check(msg.as_bytes())

    def test_inline_docx_cannot_replace_or_duplicate_direct_attachment(self):
        msg = BytesParser(policy=policy.default).parsebytes(draft())
        msg.get_payload()[-1].replace_header(
            "Content-Disposition", 'inline; filename="CV.docx"'
        )
        with self.assertRaisesRegex(ValueError, "direct attachment"):
            self.check(msg.as_bytes())
        msg = BytesParser(policy=policy.default).parsebytes(draft())
        msg.add_attachment(
            OLD, maintype="application", subtype="octet-stream",
            filename="stale.docx",
        )
        msg.get_payload()[-1].replace_header(
            "Content-Disposition", 'inline; filename="stale.docx"'
        )
        with self.assertRaisesRegex(ValueError, "exactly one DOCX"):
            self.check(msg.as_bytes())

    def test_nested_attached_email_does_not_count_as_direct_cv(self):
        inner = BytesParser(policy=policy.default).parsebytes(draft())
        outer = EmailMessage()
        outer["To"] = "jobs@example.org"
        outer["Subject"] = "Application"
        outer["X-Unsent"] = "1"
        outer.set_content("Outer draft has only an attached email.")
        outer.add_attachment(inner)
        with self.assertRaisesRegex(ValueError, "exactly one DOCX"):
            self.check(outer.as_bytes())

    def test_unrelated_pdf_attachment_is_allowed(self):
        msg = BytesParser(policy=policy.default).parsebytes(draft())
        msg.add_attachment(b"example", maintype="application", subtype="pdf", filename="cover.pdf")
        self.assertEqual(len(self.check(msg.as_bytes())["sha256"]), 64)

    def test_duplicate_unsent_marker_fails(self):
        raw = draft()
        self.assertIn(b"X-Unsent: 1\n", raw)
        duplicated = raw.replace(b"X-Unsent: 1\n", b"X-Unsent: 1\nX-Unsent: 1\n", 1)
        with self.assertRaisesRegex(ValueError, "X-Unsent"):
            self.check(duplicated)

    def test_multipart_docx_named_container_rejected(self):
        msg = BytesParser(policy=policy.default).parsebytes(draft())
        attached = EmailMessage()
        attached.make_mixed()
        attached.add_attachment(b"nested payload", maintype="application", subtype="octet-stream", filename="nested.bin")
        attached.add_header("Content-Disposition", "attachment", filename="stale.docx")
        msg.attach(attached)
        with self.assertRaisesRegex(ValueError, "exactly one DOCX"):
            self.check(msg.as_bytes())

    def test_invalid_base64_characters_and_padding_fail_closed(self):
        raw = draft()
        encoded = base64.b64encode(CV)
        self.assertIn(encoded, raw)
        malformed = encoded[:8] + b"!" + encoded[8:]
        with self.assertRaisesRegex(ValueError, "malformed MIME"):
            self.check(raw.replace(encoded, malformed, 1))
        self.assertTrue(encoded.endswith(b"="))
        unpadded = encoded[:-1]
        with self.assertRaisesRegex(ValueError, "malformed MIME"):
            self.check(raw.replace(encoded, unpadded, 1))

    def test_duplicate_transfer_encoding_headers_are_rejected(self):
        raw = draft()
        original = b"Content-Transfer-Encoding: base64\\n"
        self.assertIn(original, raw)
        ambiguous = raw.replace(
            original,
            original + b"Content-Transfer-Encoding: quoted-printable\\n",
            1,
        )
        with self.assertRaisesRegex(ValueError, "malformed MIME"):
            self.check(ambiguous)

    def test_inline_encapsulated_message_types_cannot_supply_cv(self):
        inner = BytesParser(policy=policy.default).parsebytes(draft())
        for subtype in ("global", "news"):
            with self.subTest(subtype=subtype):
                outer = EmailMessage()
                outer["To"] = "jobs@example.org"
                outer["Subject"] = "Application"
                outer["X-Unsent"] = "1"
                outer.set_content("The CV is nested inside another message.")
                outer.add_attachment(inner, subtype=subtype)
                outer.get_payload()[-1].replace_header("Content-Disposition", "inline")
                with self.assertRaisesRegex(ValueError, "exactly one DOCX"):
                    self.check(outer.as_bytes())
