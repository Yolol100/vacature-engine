"""Read-only, Register-owned coverage planner for bounded free vacancy discovery.

Source entries are *not* proof of a scanned website. A Google search for a
domain is only a discovery hint, not an official employer page verification.
This module does not access the network, score candidates or change lifecycle.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit

MAX_GOOGLE_QUERIES = 20
MAX_GOOGLE_REQUESTS = 50
_TERM = re.compile(r"[a-z0-9][a-z0-9 .+&/_-]{1,69}\Z", re.I)
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z", re.I)
_UNSAFE_SUFFIXES = (".local", ".internal", ".localhost", ".test", ".invalid")
_INACTIVE = {"retired", "consolidated"}
_NOT_VACANCY = {"application_evidence"}


def _domain(value: str, *, url: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        if url:
            parsed = urlsplit(value.strip())
            if parsed.scheme not in {"https", "http"} or parsed.username or parsed.password:
                return None
            if parsed.port not in {None, 80, 443}:
                return None
            host = parsed.hostname or ""
        else:
            host = value.strip().casefold()
        host = host.lower().rstrip(".")
        if (not host or len(host) > 253 or "." not in host
                or host.endswith(_UNSAFE_SUFFIXES)):
            return None
        labels = host.split(".")
        if not all(_LABEL.fullmatch(part) for part in labels):
            return None
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            return None
        return host
    except ValueError:
        return None


def _csv(value: str) -> list[str]:
    if not isinstance(value, str):
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _terms(config: dict[str, str]) -> list[str]:
    values = _csv(config.get("target_role_search_terms", "")) + _csv(
        config.get("vacancy_specialized_search_terms", ""))
    seen: set[str] = set()
    result = []
    for term in values:
        key = term.casefold()
        if key not in seen and _TERM.fullmatch(term):
            result.append(term)
            seen.add(key)
    return result


def build_source_coverage(
    register_rows: list[dict[str, str]],
    deploy_specs: list[dict[str, Any]],
    config: dict[str, str],
    google_seed_queries: list[str],
    *,
    round_index: int,
    max_google_queries: int,
    pages: int,
) -> dict[str, Any]:
    """Plan bounded, rotating *discovery*, not a claim of full source scans.

    The round is explicit/reproducible: use round_index+1 on the next manual
    run. No paid provider or background schedule is started.
    """
    if (type(round_index) is not int or round_index < 0
            or type(max_google_queries) is not int
            or not 1 <= max_google_queries <= MAX_GOOGLE_QUERIES
            or type(pages) is not int or pages not in {0, 1, 3, 10}):
        raise ValueError("Invalid bounded coverage plan")
    ids: set[str] = set()
    active_ids = {
        str(row.get("source_id") or "").strip()
        for row in register_rows
        if str(row.get("status") or "").strip().casefold() == "active"
    }
    adapters: set[str] = set()
    for spec in deploy_specs:
        if not isinstance(spec, dict) or not spec.get("adapter") or (
                spec.get("adapter") == "serpapi_google"):
            continue
        ident = str(spec.get("source_id") or "").strip()
        required = {ident}
        extra = (spec.get("options") or {}).get("registry_source_id")
        if isinstance(extra, str) and extra.strip():
            required.add(extra.strip())
        elif isinstance(extra, list):
            required.update(str(x).strip() for x in extra if str(x).strip())
        if ident and required.issubset(active_ids):
            # Count the approved provider AND its employer-specific Register
            # IDs: one ATS request may cover a registered employer source.
            adapters.update(required)
    entries = []
    public = []
    priorities = {"high": 0, "medium": 1, "low": 2}
    high_order = _csv(config.get("high_source_order", ""))
    for row in register_rows:
        source_id = str(row.get("source_id") or "").strip()
        if not source_id or source_id in ids:
            raise ValueError("Missing or duplicate Register source id")
        ids.add(source_id)
        status = str(row.get("status") or "").strip().casefold()
        kind = str(row.get("source_type") or "").strip()
        priority = str(row.get("priority") or "").strip().casefold()
        host = _domain(row.get("base_url", ""), url=True)
        item = {
            "source_id": source_id, "registry_status": status,
            "source_type": kind, "priority": priority,
            "coverage_route": "unavailable", "execution": "not_attempted",
        }
        if status in _INACTIVE:
            item["coverage_route"] = "excluded_inactive"
            item["execution"] = "excluded"
        elif status != "active":
            item["coverage_route"] = "excluded_unrecognized_status"
            item["execution"] = "excluded"
        elif kind in _NOT_VACANCY:
            item["coverage_route"] = "non_vacancy_evidence"
            item["execution"] = "not_applicable"
        elif source_id in adapters:
            item["coverage_route"] = "public_adapter"
        elif source_id == "google-jobs":
            item["coverage_route"] = "free_google_optional"
        elif host:
            item["coverage_route"] = "google_site_discovery_only"
            public.append((item, host))
        else:
            item["coverage_route"] = "missing_safe_public_site"
        entries.append(item)

    public.sort(key=lambda pair: (
        priorities.get(pair[0]["priority"], 3),
        high_order.index(pair[0]["source_id"])
        if pair[0]["source_id"] in high_order else len(high_order),
        pair[0]["source_id"],
    ))
    terms = _terms(config)
    xray_domains = list(dict.fromkeys(
        host for host in (_domain(part) for part in _csv(
            config.get("google_xray_domains", ""))) if host))
    seeds = list(dict.fromkeys(
        query.strip() for query in google_seed_queries
        if isinstance(query, str) and 3 <= len(query.strip()) <= 300))
    # One query costs up to "pages" free searches; provider enforces a second
    # free account/quota/rate check before any request.
    budget = min(max_google_queries, MAX_GOOGLE_QUERIES,
                 MAX_GOOGLE_REQUESTS // max(1, pages))
    queries: list[dict[str, str]] = []
    seen_queries: set[str] = set()

    def add(query: str, lane: str, source_id: str = "") -> None:
        if (len(queries) >= budget or not 3 <= len(query) <= 300
                or query.casefold() in seen_queries):
            return
        seen_queries.add(query.casefold())
        queries.append({"query": query, "lane": lane, "source_id": source_id})

    source_slots = min(len(public), max(1, budget // 2)) if public and terms else 0
    xray_slots = min(budget - source_slots, max(1, budget // 3)) if xray_domains and terms else 0
    for j in range(source_slots):
        index = (round_index * source_slots + j) % len(public)
        item, host = public[index]
        term = terms[((round_index * source_slots + j) // len(public)) % len(terms)]
        add(f'site:{host} "{term}" remote', "registered_source_domain", item["source_id"])
    total_pairs = len(xray_domains) * len(terms)
    for j in range(xray_slots):
        index = (round_index * xray_slots + j) % total_pairs
        host = xray_domains[index % len(xray_domains)]
        term = terms[index // len(xray_domains)]
        add(f'site:{host} "{term}" remote', "configured_xray_domain")
    if seeds:
        for j in range(len(seeds)):
            add(seeds[(round_index + j) % len(seeds)], "registered_google_seed")
    # Spend remaining permitted slots on rotating X-ray pairs, not repeats.
    if total_pairs:
        for j in range(xray_slots, min(total_pairs + xray_slots, budget * 5)):
            if len(queries) >= budget:
                break
            index = (round_index * xray_slots + j) % total_pairs
            add(f'site:{xray_domains[index % len(xray_domains)]} '
                f'"{terms[index // len(xray_domains)]}" remote', "configured_xray_domain")
    planned_ids = {q["source_id"] for q in queries if q["source_id"]}
    for item in entries:
        if item["source_id"] in planned_ids:
            item["execution"] = "google_query_planned_not_executed"
    summary = {
        "registered_total": len(entries),
        "active_total": sum(x["registry_status"] == "active" for x in entries),
        "inactive_total": sum(x["registry_status"] in _INACTIVE for x in entries),
        "adapter_registered": sum(x["coverage_route"] == "public_adapter" for x in entries),
        "google_site_eligible": len(public),
        "google_site_planned": len(planned_ids),
        "google_site_unplanned": len(public) - len(planned_ids),
        "non_vacancy": sum(x["coverage_route"] == "non_vacancy_evidence" for x in entries),
        "unavailable_public_site": sum(x["coverage_route"] == "missing_safe_public_site"
                                       for x in entries),
    }
    return {
        "schema": "registered-source-coverage.v1",
        "round_index": round_index,
        "google_request_budget": len(queries) * pages,
        "google_query_count": len(queries),
        "specialized_search_terms": len(terms),
        "configured_xray_domains": len(xray_domains),
        "possible_xray_pairs": total_pairs,
        "query_plan": queries,
        "sources": entries,
        "summary": summary,
    }


def complete_source_coverage(
    plan: dict[str, Any], *,
    google_status: str,
    source_attempts: list[dict[str, Any]],
    mode: str,
) -> dict[str, Any]:
    """Return actual adapter attempts and separate Google *batch* evidence.

    Google adapter observations do not prove every planned query was executed.
    No source without its own adapter is ever labeled as directly scanned.
    """
    result = {**plan, "sources": [dict(row) for row in plan["sources"]]}
    attempts: dict[str, list[dict[str, Any]]] = {}
    for attempt in source_attempts:
        if not isinstance(attempt, dict):
            continue
        ids = attempt.get("registry_source_ids") or []
        if not isinstance(ids, list):
            ids = []
        for source_id in ids:
            if isinstance(source_id, str):
                attempts.setdefault(source_id, []).append(attempt)
        # Older source attempts without registry IDs may use source_id:tenant.
        if not ids and isinstance(attempt.get("source_instance"), str):
            src = attempt["source_instance"].split(":", 1)[0]
            attempts.setdefault(src, []).append(attempt)
    for row in result["sources"]:
        source_id = row["source_id"]
        own = attempts.get(source_id, [])
        if row["coverage_route"] == "public_adapter":
            if own:
                row["execution"] = ("direct_attempt_succeeded"
                                    if any(x.get("success") is True for x in own)
                                    else "direct_attempt_failed")
            elif mode != "check":
                row["execution"] = "not_selected_within_round_limit"
        elif row["coverage_route"] == "free_google_optional":
            if google_status == "searched":
                row["execution"] = "google_provider_batch_succeeded"
            elif google_status not in {"ready", "not_registered"}:
                row["execution"] = "google_provider_" + google_status
        elif row["execution"] == "google_query_planned_not_executed" and mode != "check":
            row["execution"] = (
                "google_batch_succeeded_query_unconfirmed"
                if google_status == "searched" else
                "google_query_not_executed_or_provider_blocked"
            )
    counts: dict[str, int] = {}
    for row in result["sources"]:
        state = row["execution"]
        counts[state] = counts.get(state, 0) + 1
    result["execution_counts"] = counts
    result["google_status"] = google_status
    result["mode"] = mode
    return result
