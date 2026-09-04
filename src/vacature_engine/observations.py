from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

OBSERVATION_CONTRACT_VERSION = "1.0"

# Stable evidence-class preference only. Mutable source IDs/priorities stay in the Vacature Register.
_SOURCE_CLASS_RANK = {
    "employer_direct": 0,
    "ats": 1,
    "job_board": 2,
    "wordpress_discovery": 2,
    "discovery_api": 3,
    "discovery": 4,
    "search": 5,
}

_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "msclkid",
}


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.strip().split())
    return text or None


def _fold_text(value: Any) -> str | None:
    text = _clean_text(value)
    return text.casefold() if text else None


def normalize_canonical_url(value: Any) -> str | None:
    """Normalize a public HTTP(S) vacancy URL without performing network I/O.

    Only known tracking parameters and fragments are removed. Semantic query
    parameters are preserved because some ATS/job-board URLs use them as identity.
    """
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if scheme not in {"http", "https"} or not host:
        return None

    port = parts.port
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"

    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"

    query_items = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        folded = key.casefold()
        if folded.startswith("utm_") or folded in _TRACKING_QUERY_KEYS:
            continue
        query_items.append((key, val))
    query_items.sort()

    return urlunsplit((scheme, netloc, path, urlencode(query_items, doseq=True), ""))


def _source_job_key(row: Mapping[str, Any]) -> str | None:
    source_id = _fold_text(row.get("source_id"))
    source_job_id = _fold_text(row.get("source_job_id"))
    if source_id and source_job_id:
        return f"source:{source_id}:{source_job_id}"
    return None


def _fallback_fingerprint(row: Mapping[str, Any]) -> str | None:
    employer = _fold_text(row.get("employer"))
    title = _fold_text(row.get("title"))
    location = _fold_text(row.get("location")) or ""
    if not employer or not title:
        return None
    raw = "\x1f".join((employer, title, location)).encode("utf-8")
    return "fingerprint:" + sha256(raw).hexdigest()


def observation_identity_keys(row: Mapping[str, Any]) -> tuple[str, ...]:
    keys: list[str] = []
    url = normalize_canonical_url(row.get("canonical_url") or row.get("url"))
    if url:
        keys.append(f"url:{url}")
    source_key = _source_job_key(row)
    if source_key:
        keys.append(source_key)
    fingerprint = _fallback_fingerprint(row)
    if fingerprint:
        keys.append(fingerprint)
    return tuple(keys)


def _authority_key(row: Mapping[str, Any]) -> tuple[int, int, int, int, str, str]:
    source_type = _fold_text(row.get("source_type")) or ""
    rank = _SOURCE_CLASS_RANK.get(source_type, 99)
    canonical_url = normalize_canonical_url(row.get("canonical_url") or row.get("url"))
    return (
        rank,
        0 if canonical_url else 1,
        0 if _clean_text(row.get("source_job_id")) else 1,
        0 if _clean_text(row.get("published_at")) else 1,
        _fold_text(row.get("source_id")) or "",
        canonical_url or "",
    )


def _time_value(value: Any) -> str | None:
    # Observation timestamps are transport/provenance values. Keep them opaque;
    # callers that need strict timestamp validation should do that before this layer.
    return _clean_text(value)


def _choose_published_at(cluster: Sequence[Mapping[str, Any]]) -> str | None:
    for row in sorted(cluster, key=_authority_key):
        published = _clean_text(row.get("published_at"))
        if published:
            return published
    return None


def _merge_cluster(cluster: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted(cluster, key=_authority_key)
    chosen = dict(ordered[0])
    chosen_url = normalize_canonical_url(chosen.get("canonical_url") or chosen.get("url"))
    if chosen_url:
        chosen["canonical_url"] = chosen_url

    published_at = _choose_published_at(cluster)
    # Critical invariant: first_seen_at is never promoted to publication evidence.
    chosen["published_at"] = published_at

    first_seen_values = sorted(v for row in cluster if (v := _time_value(row.get("first_seen_at"))))
    last_seen_values = sorted(v for row in cluster if (v := _time_value(row.get("last_seen_at"))))
    chosen["first_seen_at"] = first_seen_values[0] if first_seen_values else None
    chosen["last_seen_at"] = last_seen_values[-1] if last_seen_values else None

    source_ids = sorted({v for row in cluster if (v := _clean_text(row.get("source_id")))})
    source_urls = sorted(
        {
            v
            for row in cluster
            if (v := normalize_canonical_url(row.get("canonical_url") or row.get("url")))
        }
    )
    chosen["source_ids"] = source_ids
    chosen["source_urls"] = source_urls
    chosen["observation_count"] = len(cluster)
    chosen["observation_contract_version"] = OBSERVATION_CONTRACT_VERSION
    return chosen


def canonicalize_observations(observations: Sequence[Any]) -> list[dict[str, Any]]:
    """Cluster same-run observations deterministically and select a canonical record.

    This function performs no crawling, no semantic fit assessment, no cross-run
    persistence, and no source-priority lookup. External vacancy text remains data.
    """
    rows: list[Mapping[str, Any]] = [row for row in observations if isinstance(row, Mapping)]
    if not rows:
        return []

    parent = list(range(len(rows)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left == root_right:
            return
        if root_left < root_right:
            parent[root_right] = root_left
        else:
            parent[root_left] = root_right

    key_owner: dict[str, int] = {}
    for index, row in enumerate(rows):
        for key in observation_identity_keys(row):
            if key in key_owner:
                union(index, key_owner[key])
            else:
                key_owner[key] = index

    groups: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[find(index)].append(row)

    merged = [_merge_cluster(cluster) for cluster in groups.values()]
    merged.sort(
        key=lambda row: (
            _fold_text(row.get("employer")) or "",
            _fold_text(row.get("title")) or "",
            normalize_canonical_url(row.get("canonical_url") or row.get("url")) or "",
        )
    )
    return merged
