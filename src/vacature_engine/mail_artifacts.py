"""Read-only MIME-to-CV integrity gate for externally generated .eml drafts.

Mail composition, document rendering, candidate claims, application status and
sending are outside the vacancy engine. No personal application content is stored.
"""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from pathlib import PurePath

from .cv_artifacts import CV_ARTIFACT_MIME, sha256_bytes


def _outer_message_parts(message):
    """Visit outer parts; count named containers but never enter attached content."""
    if message.get_content_maintype() == "message":
        yield message
        return
    if message.is_multipart():
        for part in message.iter_parts():
            if part.get_content_maintype() == "message" or (
                part.get_content_disposition() == "attachment" and part.is_multipart()
            ):
                yield part
                continue
            yield from _outer_message_parts(part)
    else:
        yield message


def _is_docx_candidate(part):
    """Include inline DOCX, mislabeled filename and DOCX MIME duplicates."""
    name = part.get_filename() or ""
    return name.lower().endswith(".docx") or part.get_content_type() == CV_ARTIFACT_MIME


def verify_unsent_eml_cv(
    eml_bytes: bytes,
    expected_cv_bytes: bytes,
    *,
    expected_filename: str,
    expected_recipient: str | None = None,
    expected_subject: str | None = None,
    require_unsent: bool = True,
) -> dict[str, str]:
    """Verify the final MIME draft includes exactly the current DOCX bytes.

    The caller supplies trusted current CV bytes and optional expected headers.
    A pass is integrity evidence only; it never proves a mail was sent or the CV
    is factually correct. Fail closed if a stale/different CV is embedded.
    """
    if not isinstance(eml_bytes, bytes) or not isinstance(expected_cv_bytes, bytes):
        raise TypeError("eml_bytes and expected_cv_bytes must be bytes")
    if not eml_bytes or not expected_cv_bytes:
        raise ValueError("eml_bytes and expected_cv_bytes cannot be empty")
    if not isinstance(expected_filename, str) or not expected_filename.endswith(".docx"):
        raise ValueError("expected_filename must be a .docx basename")
    if PurePath(expected_filename).name != expected_filename or "\\" in expected_filename:
        raise ValueError("expected_filename must not contain a path")

    message = BytesParser(policy=policy.default).parsebytes(eml_bytes)
    unsent_headers = message.get_all("X-Unsent", [])
    if require_unsent and (len(unsent_headers) != 1 or str(unsent_headers[0]).strip() != "1"):
        raise ValueError("local .eml must be explicitly marked X-Unsent: 1")

    subjects = message.get_all("Subject", [])
    if len(subjects) > 1:
        raise ValueError("duplicate email subject headers are not allowed")
    if expected_subject is not None and (
        len(subjects) != 1 or str(subjects[0]) != expected_subject
    ):
        raise ValueError("email subject does not match intended subject")

    if expected_recipient is not None:
        if not isinstance(expected_recipient, str) or not expected_recipient.strip():
            raise ValueError("expected_recipient must be one non-empty address")
        to_headers = message.get_all("To", [])
        extra_destinations = ("Cc", "Bcc", "Resent-To", "Resent-Cc", "Resent-Bcc")
        if len(to_headers) != 1 or any(message.get_all(h, []) for h in extra_destinations):
            raise ValueError("recipient does not match intended recipient")
        actual = getaddresses(to_headers)
        if len(actual) != 1 or actual[0][1].strip().lower() != expected_recipient.strip().lower():
            raise ValueError("recipient does not match intended recipient")

    cv_parts = [
        part for part in _outer_message_parts(message)
        if _is_docx_candidate(part)
    ]
    if len(cv_parts) != 1:
        raise ValueError("exactly one DOCX CV attachment is required")
    actual_cv = cv_parts[0]
    if actual_cv.get_content_disposition() != "attachment":
        raise ValueError("DOCX CV must be a direct attachment")
    if actual_cv.get_filename() != expected_filename:
        raise ValueError("embedded CV filename does not match current CV")
    if actual_cv.get_content_type() != CV_ARTIFACT_MIME:
        raise ValueError("unexpected CV attachment MIME type")
    if len(actual_cv.get_all("Content-Transfer-Encoding", [])) != 1:
        raise ValueError("malformed MIME or CV transfer encoding")
    actual_bytes = actual_cv.get_payload(decode=True)
    if message.defects or actual_cv.defects:
        raise ValueError("malformed MIME or CV transfer encoding")
    if actual_bytes is None or sha256_bytes(actual_bytes) != sha256_bytes(expected_cv_bytes):
        raise ValueError("embedded CV content is stale or differs from current CV")
    return {"filename": expected_filename, "sha256": sha256_bytes(actual_bytes)}
