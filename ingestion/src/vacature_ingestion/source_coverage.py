from __future__ import annotations

from collections import Counter
from typing import Any

from .registry_filter import required_registry_ids

_WEB_DISCOVERY_TYPES = {
    "ats",
    "discovery",
    "discovery_api",
    "employer_direct",
    "job_board",
    "wordpress_directory",
    "wordpress_discovery",
}
_MAILBOX_TYPES = {"application_evidence"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _automated_registry_ids(specs: list[dict[str, Any]], active_ids: set[str]) -> set[str]:
    automated: set[str] = set()
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        required = required_registry_ids(spec)
        if required and required.issubset(active_ids):
            automated.update(required)
    return automated


def build_source_coverage(
    specs: list[dict[str, Any]],
    active_rows: list[dict[str, str]],
) -> dict[str, Any]:
    active_ids = {_clean(row.get("source_id")) for row in active_rows if _clean(row.get("source_id"))}
    automated_ids = _automated_registry_ids(specs, active_ids)
    sources: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for row in sorted(active_rows, key=lambda item: _clean(item.get("source_id")).casefold()):
        source_id = _clean(row.get("source_id"))
        source_type = _clean(row.get("source_type"))
        base_url = _clean(row.get("base_url"))
        if source_id in automated_ids:
            mode = "github_adapter"
            reason = "active source is represented by a verified repository adapter/spec"
        elif source_type in _MAILBOX_TYPES:
            mode = "mailbox_read_only"
            reason = "application-evidence sources are reconciled by the mailbox workflow, not vacancy ingestion"
        elif source_type in _WEB_DISCOVERY_TYPES and base_url:
            mode = "live_web_required"
            reason = "no dedicated repository adapter; route to the caller's live public web/X-ray discovery"
        elif source_type in _WEB_DISCOVERY_TYPES:
            mode = "blocked_missing_base_url"
            reason = "active discovery source has no base_url and cannot be routed safely"
        else:
            mode = "blocked_unknown_source_type"
            reason = "active source type has no declared execution route"

        counts[mode] += 1
        sources.append({
            "source_id": source_id,
            "source_name": _clean(row.get("source_name")),
            "source_type": source_type,
            "base_url": base_url or None,
            "priority": _clean(row.get("priority")) or None,
            "access_mode": _clean(row.get("access_mode")) or None,
            "allowed_listing_languages": _clean(row.get("allowed_listing_languages")) or None,
            "execution_mode": mode,
            "reason": reason,
        })

    blocked_modes = {"blocked_missing_base_url", "blocked_unknown_source_type"}
    blocked = [row for row in sources if row["execution_mode"] in blocked_modes]
    live_web_queue = [row for row in sources if row["execution_mode"] == "live_web_required"]
    return {
        "schema_version": 1,
        "active_source_count": len(sources),
        "coverage_complete": not blocked and len(sources) == len(active_ids),
        "execution_counts": dict(sorted(counts.items())),
        "automated_registry_source_ids": sorted(automated_ids),
        "live_web_queue_count": len(live_web_queue),
        "live_web_queue": live_web_queue,
        "blocked": blocked,
        "sources": sources,
    }
