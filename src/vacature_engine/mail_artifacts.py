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
    if require_unsent and message.get("X-Unsent", "").strip() != "1":
        raise ValueError("local .eml must be explicitly marked X-Unsent: 1")
    if expected_recipient is not None:
        actual = {address.lower() for _, address in getaddresses(message.get_all("To", []))}
        if expected_recipient.strip().lower() not in actual:
            raise ValueError("recipient does not match intended recipient")
    if expected_subject is not None and str(message.get("Subject", "")) != expected_subject:
        raise ValueError("email subject does not match intended subject")

    cv_parts = [
        part for part in message.walk()
        if part.get_content_disposition() == "attachment"
        and (part.get_filename() or "").lower().endswith(".docx")
    ]
    if len(cv_parts) != 1:
        raise ValueError("exactly one DOCX CV attachment is required")
    actual_cv = cv_parts[0]
    if actual_cv.get_filename() != expected_filename:
        raise ValueError("embedded CV filename does not match current CV")
    if actual_cv.get_content_type() != CV_ARTIFACT_MIME:
        raise ValueError("unexpected CV attachment MIME type")
    actual_bytes = actual_cv.get_payload(decode=True)
    if actual_bytes is None or sha256_bytes(actual_bytes) != sha256_bytes(expected_cv_bytes):
        raise ValueError("embedded CV content is stale or differs from current CV")
    return {"filename": expected_filename, "sha256": sha256_bytes(actual_bytes)}
