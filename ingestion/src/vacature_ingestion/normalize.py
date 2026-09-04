from __future__ import annotations

import html
import re
from hashlib import sha256
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "msclkid"}
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(value: Any, *, max_chars: int = 2_000_000) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.replace("\x00", " ")[:max_chars]
    text = " ".join(value.strip().split())
    return text or None


def html_to_text(value: Any, *, max_chars: int = 2_000_000) -> str | None:
    if not isinstance(value, str):
        return clean_text(value, max_chars=max_chars)
    text = _TAG_RE.sub(" ", value[:max_chars])
    return clean_text(html.unescape(text), max_chars=max_chars)


def normalize_canonical_url(value: Any) -> str | None:
    """Match vacature-engine 5.4.0 URL identity normalization."""
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
        scheme = parts.scheme.lower()
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError:
        return None
    if scheme not in {"http", "https"} or not host:
        return None
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    query_items: list[tuple[str, str]] = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        folded = key.casefold()
        if folded.startswith("utm_") or folded in _TRACKING_QUERY_KEYS:
            continue
        query_items.append((key, val))
    query_items.sort()
    return urlunsplit((scheme, netloc, path, urlencode(query_items, doseq=True), ""))


def strong_identity_keys(row: Mapping[str, Any]) -> tuple[str, ...]:
    keys: list[str] = []
    url = normalize_canonical_url(row.get("canonical_url") or row.get("url"))
    if url:
        keys.append(f"url:{url}")
    source_id = clean_text(row.get("source_id"))
    source_job_id = clean_text(row.get("source_job_id"))
    if source_id and source_job_id:
        keys.append(f"source:{source_id.casefold()}:{source_job_id.casefold()}")
    return tuple(keys)


def weak_fingerprint(row: Mapping[str, Any]) -> str | None:
    employer = clean_text(row.get("employer"))
    title = clean_text(row.get("title"))
    location = clean_text(row.get("location")) or ""
    if not employer or not title:
        return None
    raw = "\x1f".join((employer.casefold(), title.casefold(), location.casefold())).encode("utf-8")
    return "fingerprint:" + sha256(raw).hexdigest()
