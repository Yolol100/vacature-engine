"""Deterministic metadata helpers for vacancy-specific CV artifacts.

This module deliberately does not write or rewrite CV prose. Semantic tailoring,
candidate-evidence decisions, document generation and application policy remain
caller-owned.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import PurePath
from urllib.parse import urlsplit

CV_ARTIFACT_CONTRACT_VERSION = "1.0"
CV_ARTIFACT_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_bytes(data: bytes) -> str:
    """Return a lowercase SHA-256 digest for already-owned input bytes."""
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    return hashlib.sha256(data).hexdigest()


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _safe_component(value: str, *, max_length: int) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    component = re.sub(r"[^A-Za-z0-9]+", "_", ascii_value).strip("_")
    component = re.sub(r"_+", "_", component)
    if not component:
        component = "item"
    return component[:max_length].rstrip("_") or "item"


def tailored_cv_filename(
    candidate_name: str,
    employer: str,
    title: str,
    vacancy_id: str,
    *,
    max_length: int = 180,
) -> str:
    """Build a stable, path-safe DOCX filename tied to one vacancy identity."""
    candidate_name = _required_text(candidate_name, "candidate_name")
    employer = _required_text(employer, "employer")
    title = _required_text(title, "title")
    vacancy_id = _required_text(vacancy_id, "vacancy_id")
    if not isinstance(max_length, int) or max_length < 64:
        raise ValueError("max_length must be an integer >= 64")

    identity = "\x1f".join((candidate_name, employer, title, vacancy_id))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
    parts = (
        "CV",
        _safe_component(candidate_name, max_length=36),
        _safe_component(employer, max_length=48),
        _safe_component(title, max_length=84),
        digest,
    )
    stem = "_".join(parts)
    extension = ".docx"
    if len(stem) + len(extension) > max_length:
        keep = max_length - len(extension) - len(digest) - 1
        stem = f"{stem[:keep].rstrip('_')}_{digest}"
    return stem + extension


def _validate_http_url(url: str) -> str:
    url = _required_text(url, "canonical_url")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("canonical_url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("canonical_url must not contain credentials")
    return url


def _validate_sha256(value: str, field: str) -> str:
    value = _required_text(value, field).lower()
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be a 64-character SHA-256 hex digest")
    return value


def build_cv_artifact_manifest(
    *,
    candidate_name: str,
    vacancy_id: str,
    employer: str,
    title: str,
    canonical_url: str,
    source_cv_sha256: str,
    job_snapshot_sha256: str,
) -> dict[str, str]:
    """Create deterministic provenance metadata for one tailored DOCX artifact."""
    candidate_name = _required_text(candidate_name, "candidate_name")
    vacancy_id = _required_text(vacancy_id, "vacancy_id")
    employer = _required_text(employer, "employer")
    title = _required_text(title, "title")
    canonical_url = _validate_http_url(canonical_url)
    source_cv_sha256 = _validate_sha256(source_cv_sha256, "source_cv_sha256")
    job_snapshot_sha256 = _validate_sha256(job_snapshot_sha256, "job_snapshot_sha256")

    return {
        "contract_version": CV_ARTIFACT_CONTRACT_VERSION,
        "candidate_name": candidate_name,
        "vacancy_id": vacancy_id,
        "employer": employer,
        "title": title,
        "canonical_url": canonical_url,
        "source_cv_sha256": source_cv_sha256,
        "job_snapshot_sha256": job_snapshot_sha256,
        "output_file_name": tailored_cv_filename(candidate_name, employer, title, vacancy_id),
        "output_mime": CV_ARTIFACT_MIME,
    }


def cv_artifact_identity(manifest: dict[str, str]) -> str:
    """Hash a validated manifest into a stable cross-system artifact identity."""
    validate_cv_artifact_manifest(manifest)
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_cv_artifact_manifest(manifest: object) -> None:
    """Fail closed when artifact provenance or filename metadata is inconsistent."""
    if not isinstance(manifest, dict):
        raise TypeError("manifest must be a dict")
    required = {
        "contract_version",
        "candidate_name",
        "vacancy_id",
        "employer",
        "title",
        "canonical_url",
        "source_cv_sha256",
        "job_snapshot_sha256",
        "output_file_name",
        "output_mime",
    }
    missing = required - manifest.keys()
    extra = manifest.keys() - required
    if missing:
        raise ValueError(f"manifest missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"manifest contains unsupported fields: {', '.join(sorted(extra))}")
    if manifest["contract_version"] != CV_ARTIFACT_CONTRACT_VERSION:
        raise ValueError("unsupported CV artifact contract version")
    if manifest["output_mime"] != CV_ARTIFACT_MIME:
        raise ValueError("unexpected CV artifact MIME type")

    candidate_name = _required_text(manifest["candidate_name"], "candidate_name")
    vacancy_id = _required_text(manifest["vacancy_id"], "vacancy_id")
    employer = _required_text(manifest["employer"], "employer")
    title = _required_text(manifest["title"], "title")
    _validate_http_url(manifest["canonical_url"])
    _validate_sha256(manifest["source_cv_sha256"], "source_cv_sha256")
    _validate_sha256(manifest["job_snapshot_sha256"], "job_snapshot_sha256")

    output_file_name = _required_text(manifest["output_file_name"], "output_file_name")
    if PurePath(output_file_name).name != output_file_name or "/" in output_file_name or "\\" in output_file_name:
        raise ValueError("output_file_name must be a basename, not a path")
    expected = tailored_cv_filename(candidate_name, employer, title, vacancy_id)
    if output_file_name != expected:
        raise ValueError("output_file_name does not match deterministic vacancy identity")
