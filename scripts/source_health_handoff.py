"""Evidence-only health proposals for Register Bronnen (never writes Google Sheets).

Nothing in this module infers attempts from search results, successful GitHub
Actions, planned queries or zero-result source scans. A human controller can
compare exact expected fields with the live Register before a separate, explicit
authorized update; the free discovery workflow itself has read-only credentials.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

_FIELDS = frozenset({
    "last_success_at", "last_failure_at", "failure_category",
    "consecutive_failures",
})
_FAILURE_CATEGORIES = frozenset({
    "rate_limited", "timeout_or_network", "malformed_result",
    "parsing_or_adapter_failure", "other_technical_failure",
    "http_client_error", "http_server_error", "access_denied",
    "blocked_by_provider",
})


def _utc_timestamp(value: Any, asof: datetime) -> str | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return None
    when = timestamp.astimezone(timezone.utc)
    if when.year < 2020 or when > asof + timedelta(minutes=5):
        return None
    return when.isoformat().replace("+00:00", "Z")


def source_health_handoff(register_rows: list[dict[str, str]],
                          coverage: dict[str, Any],
                          source_attempts: list[dict[str, Any]], *,
                          asof: datetime | None = None) -> dict[str, Any]:
    """Return only safe, compare-and-update proposals, never implicit writes.

    Provider aliases/tenants may produce mixed success and failure in one
    round. Such a source is left neutral, not given a fabricated 'success'.
    """
    asof = asof or datetime.now(timezone.utc)
    if asof.tzinfo is None:
        raise ValueError("Audit comparison time requires a timezone")
    asof = asof.astimezone(timezone.utc)
    registered: dict[str, dict[str, str]] = {}
    for row in register_rows:
        sid = row.get("source_id")
        if not isinstance(sid, str) or not sid or sid in registered:
            raise ValueError("Register source IDs must be unique and nonempty")
        registered[sid] = row
    route = {}
    for item in coverage.get("sources", []):
        if not isinstance(item, dict):
            continue
        sid = item.get("source_id")
        if sid in registered:
            route[sid] = item.get("coverage_route")
    attempted: dict[str, list[dict[str, Any]]] = defaultdict(list)
    malformed = 0
    for raw in source_attempts:
        if not isinstance(raw, dict) or type(raw.get("success")) is not bool:
            malformed += 1
            continue
        stamp = _utc_timestamp(raw.get("started_at"), asof)
        ids = raw.get("registry_source_ids")
        if stamp is None or not isinstance(ids, list) or not ids:
            malformed += 1
            continue
        normalized = raw.get("normalized")
        if type(normalized) is not int or normalized < 0 or normalized > 100000:
            malformed += 1
            continue
        # An allowlisted provider attempt can represent multiple explicit
        # employer IDs, but never any other Google-site discovery source.
        for sid in {item for item in ids if isinstance(item, str)}:
            if (sid not in registered
                    or route.get(sid) not in {"public_adapter", "free_google_optional"}
                    or registered[sid].get("status") != "active"):
                continue
            attempted[sid].append({
                "timestamp": stamp, "success": raw["success"],
                "category": raw.get("failure_category"),
            })
    proposals = []
    mixed = 0
    stale = 0
    for sid in sorted(attempted):
        attempts = attempted[sid]
        if {x["success"] for x in attempts} == {True, False}:
            mixed += 1
            continue
        outcome = attempts[0]["success"]
        latest = max(x["timestamp"] for x in attempts)
        row = registered[sid]
        field = "last_success_at" if outcome else "last_failure_at"
        old = row.get(field, "") or ""
        existing = _utc_timestamp(old, asof) if old else None
        if old and (existing is None or existing >= latest):
            stale += 1
            continue
        updates = {field: latest}
        if outcome:
            updates["consecutive_failures"] = "0"
            updates["failure_category"] = ""
        else:
            previous = row.get("consecutive_failures", "") or ""
            if not previous.isdigit() or len(previous) > 7:
                malformed += 1
                continue
            updates["consecutive_failures"] = str(int(previous) + 1)
            # A failure is documented even if the provider did not supply a
            # recognized safe category. Do not log raw exception text.
            categories = {x["category"] for x in attempts
                          if isinstance(x["category"], str)
                          and x["category"] in _FAILURE_CATEGORIES}
            if len(categories) == 1:
                updates["failure_category"] = next(iter(categories))
        if not set(updates).issubset(_FIELDS):
            raise ValueError("Attempted to update a non-health field")
        proposals.append({
            "source_id": sid,
            "kind": "verified_direct_attempt" if route[sid] == "public_adapter"
                    else "verified_free_google_provider_attempt",
            "outcome": "success" if outcome else "failure",
            "evidence_timestamp": latest,
            "expected": {key: row.get(key, "") or "" for key in updates},
            "proposed": updates,
        })
    unknown = sum(
        row.get("status") == "active" and not row.get("last_success_at")
        and not row.get("last_failure_at") for row in registered.values()
    )
    return {
        "schema": "source-health-proposals.v1",
        "read_only": True,
        "auto_write": False,
        "registry_active_sources_without_health_time": unknown,
        "source_attempts_received": len(source_attempts),
        "proposed_source_count": len(proposals),
        "mixed_source_skipped": mixed,
        "stale_source_skipped": stale,
        "invalid_attempt_skipped": malformed,
        "proposals": proposals,
        "application_statuses_unchanged": True,
    }
