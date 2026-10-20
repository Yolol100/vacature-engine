"""Evidence-only health proposals for Register Bronnen (never writes Google Sheets).

Nothing in this module infers attempts from search results, successful GitHub
Actions, planned queries or zero-result source scans. A human controller can
compare exact expected fields with the live Register before a separate, explicit
authorized update; the free discovery workflow itself has read-only credentials.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

_FIELDS = frozenset({
    "last_success_at", "last_failure_at", "failure_category",
    "consecutive_failures",
})
# Actual Bronnen!I data validation allows only these literal labels. Internal
# provider error codes are never written directly into this Register field.
_CATEGORY_MAP = {
    "rate_limited": "robots/access restriction",
    "timeout_or_network": "timeout/transient network",
    "malformed_result": "malformed result",
    "parsing_or_adapter_failure": "parsing/structure change",
    "other_technical_failure": "other technical failure",
    "http_client_error": "other technical failure",
    "http_server_error": "other technical failure",
    "access_denied": "robots/access restriction",
    "blocked_by_provider": "robots/access restriction",
}
_VALID_REGISTER_CATEGORIES = frozenset({
    "", "blocked/login-required", "CAPTCHA", "robots/access restriction",
    "paywall", "timeout/transient network", "malformed result",
    "parsing/structure change", "other technical failure",
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
        other_field = "last_failure_at" if outcome else "last_success_at"
        other = row.get(other_field, "") or ""
        previous_other = _utc_timestamp(other, asof) if other else None
        if ((old and (existing is None or existing >= latest))
                or (other and (previous_other is None or previous_other > latest))):
            stale += 1
            continue
        old_category = row.get("failure_category", "") or ""
        old_counter = row.get("consecutive_failures", "") or ""
        if (old_category not in _VALID_REGISTER_CATEGORIES
                or not old_counter.isdigit() or len(old_counter) > 7):
            malformed += 1
            continue
        updates: dict[str, Any] = {field: latest}
        if outcome:
            updates["consecutive_failures"] = 0
            updates["failure_category"] = ""
        else:
            updates["consecutive_failures"] = int(old_counter) + 1
            # Generic category for unknown/mixed provider failure codes; no
            # raw error text, and every value matches the live Sheets enum.
            categories = {_CATEGORY_MAP[x["category"]] for x in attempts
                          if isinstance(x["category"], str)
                          and x["category"] in _CATEGORY_MAP}
            updates["failure_category"] = (
                next(iter(categories)) if len(categories) == 1
                else "other technical failure"
            )
        if not set(updates).issubset(_FIELDS):
            raise ValueError("Attempted to update a non-health field")
        expected = {key: (int(old_counter) if key == "consecutive_failures"
                          else row.get(key, "") or "") for key in updates}
        proposals.append({
            "source_id": sid,
            "kind": "verified_direct_attempt" if route[sid] == "public_adapter"
                    else "verified_free_google_provider_attempt",
            "outcome": "success" if outcome else "failure",
            "evidence_timestamp": latest,
            "expected": expected,
            "proposed": updates,
        })
    active = [row for row in registered.values()
              if row.get("status") == "active"]
    # Missing successful provider evidence is NOT the same as having no
    # health timestamp: a failure-only source is still missing a success.
    # Neither figure infers failures or successes from public page reads.
    without_success = sum(not row.get("last_success_at") for row in active)
    failure_only = sum(
        not row.get("last_success_at") and bool(row.get("last_failure_at"))
        for row in active
    )
    unknown = without_success - failure_only
    # A source with no adapter is not a failed adapter. Preserve the
    # existing aggregate, and show precisely which execution routes remain
    # unmeasured. Unknown/missing coverage must never imply a runnable job.
    allowed_routes = {
        "public_adapter", "free_google_optional",
        "google_site_discovery_only", "missing_safe_public_site",
        "non_vacancy_evidence",
    }
    unmeasured_route_counts: Counter[str] = Counter()
    for row in active:
        if row.get("last_success_at"):
            continue
        source_route = route.get(row["source_id"])
        unmeasured_route_counts[
            source_route if source_route in allowed_routes else "unclassified"
        ] += 1
    runnable = sum(unmeasured_route_counts.get(key, 0)
                   for key in ("public_adapter", "free_google_optional"))
    return {
        "schema": "source-health-proposals.v1",
        "read_only": True,
        "auto_write": False,
        "registry_active_sources_without_health_time": unknown,
        "registry_active_sources_without_success": without_success,
        "registry_active_sources_with_failure_only": failure_only,
        "registry_active_sources_without_success_provider_routable": runnable,
        "registry_active_sources_without_success_by_route": dict(
            sorted(unmeasured_route_counts.items())),
        "source_attempts_received": len(source_attempts),
        "proposed_source_count": len(proposals),
        "mixed_source_skipped": mixed,
        "stale_source_skipped": stale,
        "invalid_attempt_skipped": malformed,
        "proposals": proposals,
        "application_statuses_unchanged": True,
    }
