"""One on-demand, read-only vacancy discovery and history preflight.

Google is optional and must be verified free. Existing active public ATS/feeds
continue when the Google key, quota or research provider is unavailable.
This is a REVIEW QUEUE, not a verified recommendation or an application.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote, urlencode, urlsplit

from vacature_engine.observations import canonicalize_observations, is_role_specific_vacancy_url
from vacature_engine.simple import VacancyPolicy, policy_from_config
from vacature_ingestion.adapters.serpapi_google import (
    _ACCOUNT_URL, _get_json, _is_safe_free_account, _safe_candidate_url,
)
from vacature_ingestion.models import SourceSpec
from vacature_ingestion.ats_resolver import resolve_ats_url
from vacature_ingestion.registry_filter import (
    _request_json, _service_account_token, active_source_rows_from_values,
    filter_source_specs,
)
from vacature_ingestion.runner import IngestionRunner, SourceRunResult
from vacature_ingestion.official_review import (
    assess_official_observation, discovery_region_conflict, geography_signal, rank_fully_verified,
)
from vacature_ingestion.official_page import fetch_official_page_evidence, verified_source_account
from vacature_ingestion.requirement_match import compare_requirements, compare_requirement_dimensions
from vacature_ingestion.final_review import (
    assessment_context, automated_ranking_blockers, validate_assessment,
)


REGISTER_ID = "1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0"
GOOGLE_MODES = {"check": 0, "page-1": 1, "page-3": 3, "page-10": 10}
SHEETS = {
    "Config": {"key", "value"},
    "Bronnen": {"source_id", "status", "source_type", "priority"},
    "Vacatures": {"vacancy_id", "status", "canonical_url", "official_url", "title", "employer"},
    "Applications": {"vacancy_id", "status", "application_url"},
    "Feedback": {"vacancy_id", "state", "applied"},
    "ApplicationEvents": {"vacancy_id", "event_type"},
    "CandidateEvidence": {"evidence_id", "claim", "active"},
    "JobSnapshots": {"vacancy_id", "canonical_url"},
}
# Source-specific rank is taken from the live Register, not duplicated here.
_ATS = {"ats"}
_FREE_DISCOVERY = {"discovery_api", "job_board", "discovery"}
_ROLE_TERMS = {
    "wordpress_ecosystem": ("wordpress", "woocommerce", "gutenberg", "elementor", "block editor"),
    "web_design_development": ("web designer", "web developer", "front-end", "frontend",
                               "ux/ui", "ui/ux", "web accessibility", "web design"),
    "ai_workflow_automation": ("workflow automation", "ai automation", "n8n",
                               "make.com", "zapier", "ai agent", "agentic workflow"),
}


class RegisterPreflightError(RuntimeError):
    """A missing or corrupt authoritative Register blocks the entire scan."""


class DiscoveryUnavailableError(RuntimeError):
    """Preserve safe source-attempt metadata while retaining a blocked run."""

    def __init__(self, report: dict[str, Any]):
        super().__init__("No permitted free discovery source succeeded")
        self.report = report


def parse_table(values: Any, required: set[str], name: str) -> list[dict[str, str]]:
    if not isinstance(values, list) or not values or not isinstance(values[0], list):
        raise RegisterPreflightError("Required Register tab is unavailable: " + name)
    header = [str(col).strip() for col in values[0]]
    if len(set(header)) != len(header) or not required.issubset(header):
        raise RegisterPreflightError("Required Register columns are missing: " + name)
    rows = []
    for value in values[1:]:
        if isinstance(value, list) and any(str(x).strip() for x in value):
            rows.append({key: str(value[i]).strip() if i < len(value) and value[i] is not None else ""
                         for i, key in enumerate(header)})
    return rows


def load_register(spreadsheet_id: str = REGISTER_ID) -> dict[str, list[dict[str, str]]]:
    """Use the ingestion package's existing read-only Google Sheets OAuth code."""
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise RegisterPreflightError("Missing read-only Register credentials")
    try:
        credentials = json.loads(raw)
        token = _service_account_token(credentials)
    except Exception:
        raise RegisterPreflightError("Cannot authenticate to the Vacature Register") from None
    tables: dict[str, list[dict[str, str]]] = {}
    for name, required in SHEETS.items():
        try:
            range_ref = quote(name + "!A1:AH2000", safe="!")
            url = ("https://sheets.googleapis.com/v4/spreadsheets/"
                   + quote(spreadsheet_id, safe="") + "/values/" + range_ref)
            result = _request_json(url, token)
            values = result.get("values") if isinstance(result, dict) else None
            tables[name] = parse_table(values, required, name)
        except RegisterPreflightError:
            raise
        except Exception:
            raise RegisterPreflightError("Cannot read required Register tab: " + name) from None
    if not tables["Bronnen"] or not tables["Config"]:
        raise RegisterPreflightError("Live Register has no source policy")
    return tables


def live_policy(tables: dict[str, list[dict[str, str]]]) -> tuple[dict[str, str], VacancyPolicy]:
    config = {row["key"]: row["value"] for row in tables["Config"] if row.get("key")}
    if config.get("cross_run_deduplication", "").casefold() != "true":
        raise RegisterPreflightError("Live cross-run deduplication is not enabled")
    try:
        policy = policy_from_config(config)
    except (TypeError, ValueError):
        raise RegisterPreflightError("Live vacancy policy is incomplete or invalid") from None
    return config, policy


def select_free_specs(raw: list[dict[str, Any]], tables: dict[str, list[dict[str, str]]],
                      config: dict[str, str], limit: int = 8, *,
                      excluded_instance_ids: set[str] | None = None) -> list[SourceSpec]:
    """Select the next active Register-approved public ATS/feed instances.

    An instance already attempted in this run must not consume another slot,
    including when its previous request failed. The caller owns the total cap.
    """
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("Free source limit must be between 1 and 20")
    excluded = excluded_instance_ids or set()
    active = active_source_rows_from_values([
        ["source_id", "status"],
        *[[row["source_id"], row["status"]] for row in tables["Bronnen"]],
    ])
    active_ids = {row["source_id"] for row in active}
    approved, _ = filter_source_specs(raw, active_ids)
    sources = {row["source_id"]: row for row in tables["Bronnen"] if row.get("status", "").lower() == "active"}
    order = [part.strip() for part in config.get("direct_discovery_order", "").split(",")]
    configured_sources = [part.strip() for part in config.get("high_source_order", "").split(",") if part.strip()]
    priorities = {"high": 0, "medium": 1, "low": 2}
    # The existing deploy source order is curated. Sorting by account name
    # discards that ordering and lets irrelevant employers displace priority
    # WordPress sources in a bounded free-only run.
    instance_order: dict[str, int] = {}
    for i, item in enumerate(raw):
        if isinstance(item, dict) and item.get("source_id") and item.get("account"):
            # Identity alone is sufficient: a malformed retired spec must not
            # be parsed after Register gating already excluded it. Duplicate
            # config entries also cannot move the first curated occurrence.
            instance_order.setdefault(f"{item['source_id']}:{item['account']}", i)
    unique: dict[str, dict[str, Any]] = {}
    for item in approved:
        if item.get("adapter") == "serpapi_google":
            continue
        if item.get("source_type") not in _ATS | _FREE_DISCOVERY:
            continue
        spec = SourceSpec.from_dict(item)
        if spec.instance_id in excluded:
            continue
        unique.setdefault(spec.instance_id, item)

    def rank(item: dict[str, Any]) -> tuple[int, int, int, int, str]:
        row = sources.get(item["source_id"], {})
        return (
            order.index(item["source_type"]) if item["source_type"] in order else 999,
            priorities.get(row.get("priority", ""), 3),
            configured_sources.index(item["source_id"])
            if item["source_id"] in configured_sources else len(configured_sources),
            instance_order.get(SourceSpec.from_dict(item).instance_id, len(raw)),
            item["source_id"] + ":" + item["account"],
        )

    ordered = sorted(unique.values(), key=rank)
    ats = [x for x in ordered if x["source_type"] in _ATS]
    feeds = [x for x in ordered if x["source_type"] in _FREE_DISCOVERY]
    if ats and feeds and limit >= 2:
        ats_limit = max(1, limit // 2)
        chosen = ats[:ats_limit] + feeds[:limit - ats_limit]
        if len(chosen) < limit:
            remainder = [x for x in ordered if x not in chosen]
            chosen.extend(remainder[:limit - len(chosen)])
    else:
        chosen = ordered[:limit]
    return [
        replace(SourceSpec.from_dict(x), max_jobs=min(int(x.get("max_jobs", 80)), 80),
                timeout_seconds=12.0, retries=1)
        for x in sorted(chosen, key=rank)
    ]


def plan_free_source_batches(raw: list[dict[str, Any]],
                             tables: dict[str, list[dict[str, str]]],
                             config: dict[str, str], *, max_sources: int,
                             batch_size: int = 8) -> list[list[SourceSpec]]:
    """Bound the whole run while making later approved employers reachable.

    Reuse the existing live source order and ATS/feed diversity in each batch;
    never synthesize new source tenants, queries, adapters or source policy.
    """
    if type(max_sources) is not int or not 1 <= max_sources <= 20:
        raise ValueError("Free source limit must be between 1 and 20")
    if type(batch_size) is not int or not 1 <= batch_size <= 8:
        raise ValueError("Free source batch size must be between 1 and 8")
    batches: list[list[SourceSpec]] = []
    selected: set[str] = set()
    while len(selected) < max_sources:
        batch = select_free_specs(
            raw, tables, config, limit=min(batch_size, max_sources - len(selected)),
            excluded_instance_ids=selected,
        )
        if not batch:
            break
        batches.append(batch)
        selected.update(spec.instance_id for spec in batch)
    return batches


def _source_attempt_audit(result: SourceRunResult) -> dict[str, Any]:
    """Allowlisted health handoff; never copy provider errors or vacancy data."""
    return {
        "source_instance": result.source_instance,
        "registry_source_ids": list(result.registry_source_ids or []),
        "started_at": result.started_at,
        "success": result.success,
        "fetched": result.fetched,
        "normalized": result.normalized,
        "quarantine_count": result.quarantine_count,
        "complete_snapshot": result.complete_snapshot,
        "failure_category": result.failure_category,
    }


def run_free_discovery_batches(runner: IngestionRunner,
                               batches: list[list[SourceSpec]], *,
                               initial_observations: list[dict[str, Any]],
                               evaluate: Callable[[list[dict[str, Any]]], dict[str, Any]],
                               target_verified: int) -> dict[str, Any]:
    """Run only the planned free batches until verified output is sufficient.

    Evaluation uses the existing caller-owned verification and ranking engine.
    Review candidates never satisfy the stop condition. Source failures consume
    a slot and do not trigger a second request or any lifecycle mutation here.
    """
    if type(target_verified) is not int or target_verified < 1:
        raise ValueError("Verified output target must be a positive integer")
    planned = {spec.instance_id for batch in batches for spec in batch}
    if len(planned) > 20 or any(len(batch) > 8 for batch in batches):
        raise ValueError("Free source plan exceeds the bounded run budget")
    if any(spec.adapter == "serpapi_google" or spec.source_type not in _ATS | _FREE_DISCOVERY
           for batch in batches for spec in batch):
        raise ValueError("Free source plan contains a non-public discovery route")

    observations = list(initial_observations)
    attempted: set[str] = set()
    attempted_order: list[str] = []
    source_attempts: list[dict[str, Any]] = []
    successes = rounds = 0
    evaluation: dict[str, Any] | None = None
    stop_reason = "planned_sources_exhausted"
    for batch in batches:
        remaining = [spec for spec in batch if spec.instance_id not in attempted]
        if not remaining:
            continue
        rounds += 1
        for source in remaining:
            # Also dedupe repeated instances within a malformed batch.
            if source.instance_id in attempted:
                continue
            attempted.add(source.instance_id)
            attempted_order.append(source.instance_id)
            result = runner.run_source(source)
            source_attempts.append(_source_attempt_audit(result))
            if result.success:
                successes += 1
                observations.extend(result.observations or [])
        # The caller canonicalizes/deduplicates cumulative observations while
        # retaining evidence from multiple sources for the same vacancy.
        evaluation = evaluate(list(observations))
        if len(evaluation.get("final_recommendations", [])) >= target_verified:
            stop_reason = "verified_target_reached"
            break
    if evaluation is None:
        evaluation = evaluate(list(observations))
    return {
        "observations": observations,
        "evaluation": evaluation,
        "fallback_sources_attempted": len(attempted),
        "fallback_sources_successful": successes,
        "fallback_batches_completed": rounds,
        "fallback_stop_reason": stop_reason,
        "attempted_source_instances": attempted_order,
        "source_attempts": source_attempts,
    }


def google_free_gate(spec: SourceSpec, pages: int) -> str:
    """Only the official free account endpoint is queried; it costs zero searches."""
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        return "not_configured"
    options = spec.options if isinstance(spec.options, dict) else {}
    raw_queries = options.get("queries", [])
    if not isinstance(raw_queries, list) or not raw_queries:
        return "invalid_query_config"
    budget = pages * len({q.strip() for q in raw_queries if isinstance(q, str)})
    if pages and (budget < 1 or budget > 50):
        return "invalid_request_budget"
    try:
        account = _get_json(_ACCOUNT_URL + "?" + urlencode({"api_key": key}), timeout=15)
    except Exception:
        return "account_unavailable"
    if not _is_safe_free_account(account, budget, 10 if pages else 0):
        return "not_verified_free_or_insufficient_quota"
    return "ready"


def _nonproduction_prefixes(config: dict[str, str]) -> tuple[str, ...]:
    if config.get("nonproduction_records_excluded_from_search_and_metrics", "").casefold() != "true":
        return ()
    return tuple(part.strip().casefold() for part in
                 config.get("nonproduction_vacancy_id_prefixes", "").split(",")
                 if part.strip())


def _is_nonproduction(row: dict[str, Any], prefixes: tuple[str, ...]) -> bool:
    return str(row.get("vacancy_id") or "").strip().casefold().startswith(prefixes)


def _history_url_keys(value: Any) -> set[str]:
    """Recognize exact ATS role aliases without treating a tenant as a job.

    Provider + tenant + job ID survives host migrations and application-route
    suffixes. This is identity evidence only, never current-role verification.
    """
    url = _safe_candidate_url(value)
    if not url:
        return set()
    keys: set[str] = set()
    resolved = resolve_ats_url(url)
    if resolved is not None and resolved["provider"] in {
        "ashby", "lever", "greenhouse", "workable", "personio", "smartrecruiters",
    }:
        provider, account = resolved["provider"], resolved["account"]
        parts = [unquote(part) for part in urlsplit(url).path.split("/") if part]
        if parts and parts[-1].casefold() in {"apply", "application"}:
            parts = parts[:-1]
        job_id = None
        if provider in {"ashby", "lever"} and len(parts) == 2:
            job_id = parts[1]
        elif provider == "greenhouse" and len(parts) == 3 and parts[1] == "jobs":
            job_id = parts[2]
        elif provider == "workable" and len(parts) == 3 and parts[1] == "j":
            job_id = parts[2]
        elif provider == "personio" and len(parts) == 2 and parts[0] == "job":
            job_id = parts[1]
        elif provider == "smartrecruiters" and len(parts) == 2:
            possible = parts[1].split("-", 1)[0]
            job_id = possible if possible.isdigit() else None
        if (not isinstance(job_id, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", job_id)
                or job_id.casefold() in {"jobs", "careers", "apply", "application", "search"}):
            # Unknown ATS route shapes may still be exact previously recorded
            # URLs (e.g. Greenhouse embed/job_app). Retain that exact identity
            # without inventing a provider job ID or accepting a tenant root.
            depth = len([part for part in urlsplit(url).path.split("/") if part])
            if is_role_specific_vacancy_url(url) and (depth >= 2 or provider == "personio"):
                return {"url:" + url}
            return set()
        keys.add(f"source:{provider}:{account.casefold()}:{job_id.casefold()}")
        keys.add("url:" + url)
    elif is_role_specific_vacancy_url(url):
        keys.add("url:" + url)
    return keys


def _scoped_source_key(row: dict[str, Any]) -> str | None:
    """Never equate job 123 at one ATS tenant with job 123 at another."""
    provider = str(row.get("source_id") or "").strip().casefold()
    job_id = str(row.get("source_job_id") or "").strip().casefold()
    if not provider or not job_id:
        return None
    instance = str(row.get("source_instance") or "").strip().casefold()
    account = ""
    if instance:
        owner, separator, account = instance.partition(":")
        if not separator or owner != provider or not account:
            return None
    if ":" in job_id:
        declared_account, _, job_id = job_id.partition(":")
        if account and declared_account != account:
            return None
        account = declared_account
    resolved = resolve_ats_url(str(row.get("canonical_url") or row.get("url") or ""))
    if resolved is not None and resolved["provider"] == provider:
        url_account = resolved["account"].casefold()
        if account and account != url_account:
            return None
        account = url_account
    if not account or not job_id:
        return None
    return f"source:{provider}:{account}:{job_id}"


def _scoped_observation_identity(row: dict[str, Any]) -> dict[str, Any]:
    """Prepare only the clustering identity; never mutate the source row."""
    item = dict(row)
    source_key = _scoped_source_key(item)
    if source_key is None:
        item.pop("source_job_id", None)
    else:
        prefix = "source:" + str(item["source_id"]).strip().casefold() + ":"
        item["source_job_id"] = source_key[len(prefix):]
    return item


def _history_identity_keys(row: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for column in ("canonical_url", "official_url", "application_url", "apply_url", "url"):
        keys.update(_history_url_keys(row.get(column)))
    # Canonicalization preserves all URLs from the source cluster.
    if isinstance(row.get("source_urls"), list):
        for url in row["source_urls"]:
            keys.update(_history_url_keys(url))
    source_key = _scoped_source_key(row)
    if source_key:
        keys.add(source_key)
    vacancy_id = str(row.get("vacancy_id") or "").strip()
    if vacancy_id:
        keys.add("vacancy:" + vacancy_id)
    return keys


def _previous_index(tables: dict[str, list[dict[str, str]]]) -> tuple[set[str], set[tuple[str, str]]]:
    """Join recorded history before indexing strong role identities.

    Feedback/events remain authoritative even when the Vacatures status lags.
    Unreviewed snapshots alone do not turn a discovered vacancy into history.
    """
    config = {row.get("key"): row.get("value", "") for row in tables["Config"]}
    statuses = {value.strip().casefold() for value in
                config.get("dedupe_previous_statuses", "").split(",") if value.strip()}
    if not statuses:
        raise RegisterPreflightError("Live dedupe status policy is missing")
    prefixes = _nonproduction_prefixes(config)
    event_types = {value.strip().casefold() for value in
                   config.get("application_event_types", "").split(",") if value.strip()}
    aliases = dict(value.strip().casefold().split("=", 1) for value in
                   config.get("application_legacy_status_aliases", "").split(",")
                   if "=" in value)

    def recorded_status(value: str) -> bool:
        normalized = value.strip().casefold()
        return normalized in statuses or aliases.get(normalized) in statuses

    def production(name: str) -> list[dict[str, str]]:
        return [row for row in tables.get(name, []) if not _is_nonproduction(row, prefixes)]

    prior_ids: set[str] = set()
    keys: set[str] = set()
    weak: set[tuple[str, str]] = set()
    history_rows = [row for row in production("Vacatures")
                    if recorded_status(row.get("status", ""))]
    # A prepared/drafted application was already reviewed; preserve the
    # existing suppression even if its Vacatures anchor is missing or stale.
    history_rows.extend(production("Applications"))
    for row in production("Feedback"):
        if (recorded_status(row.get("state", ""))
                or any(row.get(flag, "").strip().casefold() == "true"
                       and recorded_status(flag) for flag in ("applied", "interview", "offer"))):
            history_rows.append(row)
    for row in production("ApplicationEvents"):
        if (recorded_status(row.get("status_after", ""))
                or recorded_status(row.get("event_type", ""))
                or row.get("event_type", "").strip().casefold() in event_types):
            history_rows.append(row)
    prior_ids.update(row["vacancy_id"].strip() for row in history_rows
                     if row.get("vacancy_id", "").strip())
    history_rows.extend(row for row in production("Vacatures")
                        if row.get("vacancy_id", "").strip() in prior_ids)
    history_rows.extend(row for row in production("JobSnapshots")
                        if row.get("vacancy_id", "").strip() in prior_ids)
    for row in history_rows:
        keys.update(_history_identity_keys(row))
        title = row.get("title", "").strip().casefold()
        employer = row.get("employer", "").strip().casefold()
        if title and employer:
            weak.add((employer, title))
    return keys, weak


# A product name (e.g. "WordPress VIP") is not proof of a technical job.
# Exclude clear sales, recruiting and nontechnical management titles only.
_NON_TECH_BUSINESS_TITLE = re.compile(
    r"\b(?:account executive|sales development|business development|"
    r"director of professional services|customer success manager|"
    r"marketing manager|talent acquisition|recruiter|"
    r"finance manager)\b", re.I,
)


# Generic technical titles may need an ATS description to reveal the domain.
# "Account Manager", "Security Engineer" or "Talent Community" must not match
# simply because their employer's boilerplate mentions WordPress/n8n.
_GENERIC_TECH_TITLE_TERMS = (
    "software engineer", "software developer", "full stack", "full-stack",
    "fullstack", "frontend", "front end", "front-end",
    "web developer", "web designer", "cms developer", "plugin developer",
    "integration engineer", "integration developer",
    "automation engineer", "automation developer", "product engineer",
)
_ATS_DESCRIPTION_TERMS = {
    "wordpress_ecosystem": ("wordpress", "woocommerce", "gutenberg", "elementor", "block editor"),
    "web_design_development": ("web development", "web design", "frontend", "front-end",
                               "front end", "web accessibility", "ux/ui", "ui/ux"),
    "ai_workflow_automation": ("workflow automation", "ai automation", "ai agent",
                               "agentic workflow", "workflow orchestration",
                               "automation integration"),
}


def _role_hints(row: dict[str, Any], policy: VacancyPolicy) -> list[str]:
    """Strict review hints only: not eligibility or candidate fit evidence."""
    title = str(row.get("title") or "").casefold()
    if _NON_TECH_BUSINESS_TITLE.search(title):
        return []
    matched = {name for name, tokens in _ROLE_TERMS.items()
               if name in policy.target_role_families
               and any(term in title for term in tokens)}
    # Incidental employer boilerplate must never qualify unrelated job titles.
    if row.get("source_type") == "ats" and any(
        term in title for term in _GENERIC_TECH_TITLE_TERMS
    ):
        body = str(row.get("description") or "").casefold()
        matched.update(name for name, tokens in _ATS_DESCRIPTION_TERMS.items()
                       if name in policy.target_role_families
                       and any(term in body for term in tokens))
    return sorted(matched)


def _review_sort_key(row: dict[str, Any], tables: dict[str, list[dict[str, str]]]
                     ) -> tuple[int, int, str]:
    config = {r.get("key"): r.get("value", "") for r in tables["Config"]}
    order = [value.strip() for value in
             config.get("direct_discovery_order", "").split(",")]
    source_kind = ("google" if row.get("source_id") == "google-jobs"
                   else row.get("source_type"))
    priority = next((r.get("priority", "").casefold() for r in tables["Bronnen"]
                     if r.get("source_id") == row.get("source_id")
                     and r.get("status", "").casefold() == "active"), "")
    return (order.index(source_kind) if source_kind in order else 999,
            {"high": 0, "medium": 1, "low": 2}.get(priority, 3),
            str(row.get("canonical_url") or row.get("url") or ""))


def _observed_age(row: dict[str, Any], today: date) -> int | None:
    """Only explicit employer/ATS publication fields are age evidence."""
    if row.get("source_type") != "ats":
        return None
    posted = row.get("published_at")
    if not isinstance(posted, str) or len(posted) < 10:
        return None
    try:
        return (today - date.fromisoformat(posted[:10])).days
    except ValueError:
        return None


def screen_review_candidates(observations: list[dict[str, Any]],
                             tables: dict[str, list[dict[str, str]]],
                             policy: VacancyPolicy, *, today: date,
                             limit: int = 60) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Suppress prior roles; hard-exclude only explicit mismatches; keep all unknowns unverified."""
    historical_keys, weak = _previous_index(tables)
    counted = {"unapproved_source": 0, "previously_registered": 0, "possible_prior_match": 0,
               "explicit_mismatch": 0, "unsafe_link": 0, "off_target": 0,
               "official_region_rejected": 0, "source_location_restricted": 0,
               "non_job_page": 0, "source_expired": 0, "awaiting_verification": 0,
               "nonproduction": 0}
    active_ids = {r.get("source_id", "") for r in tables["Bronnen"]
                  if r.get("status", "").casefold() == "active"}
    config = {row.get("key"): row.get("value", "") for row in tables["Config"]}
    prefixes = _nonproduction_prefixes(config)
    approved: list[dict[str, Any]] = []
    identities_by_url: dict[str, set[str]] = {}
    for row in observations:
        if not isinstance(row, dict):
            continue
        # Gate before clustering: retired or test rows cannot contaminate an
        # active observation that happens to share its URL or provider ID.
        if _is_nonproduction(row, prefixes):
            counted["nonproduction"] += 1
            continue
        if row.get("source_id") not in active_ids:
            counted["unapproved_source"] += 1
            continue
        item = _scoped_observation_identity(row)
        keys = _history_identity_keys(item)
        for key in keys:
            if key.startswith("url:"):
                identities_by_url.setdefault(key, set()).update(keys)
        approved.append(item)
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Respect live source-class priorities. A Google/board title never gets to
    # crowd out official ATS evidence merely because its request finished first.
    ordered = sorted(canonicalize_observations(approved),
                     key=lambda row: _review_sort_key(row, tables))
    for row in ordered:
        url = _safe_candidate_url(row.get("canonical_url") or row.get("url"))
        if not url or not is_role_specific_vacancy_url(url):
            counted["unsafe_link"] += 1
            continue
        keys = _history_identity_keys(row)
        for key in tuple(keys):
            if key.startswith("url:"):
                keys.update(identities_by_url.get(key, set()))
        if keys & seen:
            continue
        seen.update(keys)
        if keys & historical_keys:
            counted["previously_registered"] += 1
            continue
        # A dated, explicitly expired listing is unsuitable regardless of
        # discovery provider. Missing or malformed validThrough stays unknown.
        valid_through = row.get("valid_through")
        if isinstance(valid_through, str) and len(valid_through) >= 10:
            try:
                expired = date.fromisoformat(valid_through[:10]) < today
            except ValueError:
                expired = False
            if expired:
                counted["source_expired"] += 1
                continue
        employer = str(row.get("employer") or "").strip()
        title = str(row.get("title") or "").strip()
        listing_language = str(row.get("listing_language") or "").strip().lower()
        remote = row.get("remote")
        age = _observed_age(row, today)
        # Only explicit authoritative negative signals may exclude automatically.
        if ((row.get("source_type") == "ats" and remote is False)
                or (listing_language and listing_language not in policy.allowed_listing_languages)
                or (age is not None and (age < 0 or
                    (policy.max_posting_age_days > 0 and age > policy.max_posting_age_days)))):
            counted["explicit_mismatch"] += 1
            continue
        # Freelancers advertising their own availability are not employer roles.
        # Keep the rule anchored to that narrow, demonstrable scenario.
        if (urlsplit(url).hostname or "").casefold() == "community.n8n.io" and (
            "/t/available-" in urlsplit(url).path.casefold()
        ):
            counted["non_job_page"] += 1
            continue
        # All board/feed/Google providers are discovery only. A clear negative
        # location or exclusive foreign residency condition may withhold them
        # from the shortlist, but can NEVER verify NL eligibility or close a
        # vacancy. The exact same rule applies to each existing free source.
        # A provider may return a custom employer URL (e.g. Greenhouse
        # Pantheon). Unknown official ownership does not erase an explicit
        # US-only location, and a positive location hint still proves nothing.
        if discovery_region_conflict(
            row, include_ats=verified_source_account(row, active_ids=active_ids) is None,
        ) is not None:
            counted["source_location_restricted"] += 1
            continue
        if (employer.casefold(), title.casefold()) in weak and employer and title:
            counted["possible_prior_match"] += 1
            # A different URL may be the user's previously applied role.
            continue
        hints = _role_hints(row, policy)
        if not hints:
            counted["off_target"] += 1
            continue
        # Source-backed verification checks use live official ATS observations,
        # never an aggregator's snippet or a guessed application language.
        preliminary = {
            "title": title[:400], "employer": employer[:250] or None,
            "role_family_hints": hints,
        }
        verified_signals, _rankable = assess_official_observation(
            row, candidate=preliminary, active_ids=active_ids,
            evidence=tables["CandidateEvidence"], policy=policy, today=today,
        )
        if (verified_signals["official_role"] == "confirmed_current_public_ats"
                and (verified_signals["netherlands"] == "restricted"
                     or verified_signals["remote"] == "not_remote"
                     or verified_signals["original_publication"] == "too_old")):
            counted["official_region_rejected"] += 1
            continue
        if len(output) >= limit:
            break
        # Only verified ATS-provider records can be compared with private,
        # active CandidateEvidence. The report contains counts, not claims.
        requirement_review = (
            compare_requirements(row, tables["CandidateEvidence"])
            if verified_signals["official_role"] == "confirmed_current_public_ats"
            else {
                "status": "requirements_unverified",
                "explicit_technical_requirements": 0,
                "requirements_with_candidate_evidence": 0,
                "requirements_without_candidate_evidence": 0,
                "ambiguous_or_unparsed_requirements": 0,
                "final_score_authorized": False,
            }
        )
        requirement_dimensions = (
            compare_requirement_dimensions(row, tables["CandidateEvidence"])
            if verified_signals["official_role"] == "confirmed_current_public_ats"
            else {"status": "requirements_unverified", "final_score_authorized": False}
        )
        # Third-party timestamps are discovery hints, NOT employer original
        # publication proof. Old source dates warn without auto-closing a role.
        review_alerts: list[str] = []
        if row.get("source_type") != "ats":
            observed_date = row.get("published_at")
            if isinstance(observed_date, str) and len(observed_date) >= 10:
                try:
                    days = (today - date.fromisoformat(observed_date[:10])).days
                except ValueError:
                    days = None
                if (days is not None and days >= 0
                        and policy.max_posting_age_days > 0
                        and days > policy.max_posting_age_days):
                    review_alerts.append("discovery_date_older_than_policy")
        # Private CandidateEvidence claims never leave this process.
        output.append({
            "title": title[:400], "employer": employer[:250] or None,
            "official_role_candidate_url": url,
            "source_types": row.get("source_types") or [row.get("source_type")],
            "role_family_hints": hints,
            "official_checks": verified_signals,
            "technical_requirement_review": requirement_review,
            "requirement_dimensions": requirement_dimensions,
            "review_alerts": review_alerts,
            "status": "unverified_review_only",
            "still_to_verify": [
                "official_employer_and_exact_open_role", "original_publication_date",
                "fully_remote_and_allowed_from_netherlands", "work_and_application_language",
                "candidate_evidence_fit_and_score", "application_route",
            ],
        })
        counted["awaiting_verification"] += 1
    # Higher-confidence official ATS roles first within the review queue.
    # This is review order, NOT final candidate-fit or salary ranking.
    output.sort(key=lambda x: (
        0 if x["official_checks"]["official_role"] == "confirmed_current_public_ats" else 1,
        0 if x["official_checks"]["netherlands"] == "allowed" else 1,
        0 if x["official_checks"]["remote"] == "confirmed" else 1,
        x["official_role_candidate_url"],
    ))
    return output, counted


def _official_page_exclusion(page: dict[str, Any], policy: VacancyPolicy,
                             today: date) -> str | None:
    """Only definitive first-party closure/expiry/old-original proof can drop a role."""
    if page.get("status") == "closed_at_exact_ats_route":
        return "official_job_route_closed"
    if page.get("status") != "matching_first_party_jobposting":
        return None
    info = page.get("structured")
    if not isinstance(info, dict):
        return None
    if info.get("expired_by_valid_through") is True:
        return "official_job_expired"
    posted = info.get("date_posted")
    if isinstance(posted, str) and info.get("date_posted_valid") is True:
        try:
            age = (today - date.fromisoformat(posted)).days
        except ValueError:
            return None
        if age >= 0 and policy.max_posting_age_days > 0 and age > policy.max_posting_age_days:
            return "official_original_post_too_old"
    return None


def _missing_ranking_evidence(candidate: dict[str, Any],
                              page: dict[str, Any], policy: VacancyPolicy,
                              today: date) -> list[str]:
    """Compatibility wrapper for the single mandatory ranking gate contract."""
    return automated_ranking_blockers(candidate, page, policy, today)


def evaluate_observations(observations: list[dict[str, Any]],
                          tables: dict[str, list[dict[str, str]]],
                          config: dict[str, str], policy: VacancyPolicy, *, today: date,
                          assessments: dict[str, dict[str, Any]],
                          page_cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Reuse screening, fetch each official page at most once, then rank proof."""
    candidates, counts = screen_review_candidates(
        observations, tables, policy, today=today,
        limit=max(20, min(100, policy.max_output_roles * 12)),
    )
    active_ids = {r["source_id"] for r in tables["Bronnen"]
                  if r.get("status", "").casefold() == "active"}
    # Use the same canonical identity as screening. Tracking parameters or
    # trailing slashes must not disconnect a genuine role from its evidence.
    prefixes = _nonproduction_prefixes(config)
    scoped_originals = [
        {**_scoped_observation_identity(row), "_source_job_id_before_clustering": row.get("source_job_id")}
        for row in observations if isinstance(row, dict)
        and not _is_nonproduction(row, prefixes)
        and verified_source_account(row, active_ids=active_ids) is not None
    ]
    originals: dict[str, dict[str, Any]] = {}
    for original in canonicalize_observations(scoped_originals):
        # Scope IDs for clustering, then retain the selected source's actual
        # field value in its evidence digest. This preserves private handoff
        # compatibility with a legacy observation using an unprefixed job ID.
        original["source_job_id"] = original.pop("_source_job_id_before_clustering")
        originals[original["canonical_url"]] = original
    exclusions = {"official_job_route_closed": 0, "official_job_expired": 0,
                  "official_original_post_too_old": 0,
                  "verified_mandatory_requirement_mismatch": 0,
                  "verified_below_live_thresholds": 0}
    pending: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    for candidate in candidates:
        url = candidate["official_role_candidate_url"]
        original = originals.get(url)
        if (original is None or candidate["official_checks"]["official_role"]
                != "confirmed_current_public_ats"):
            pending.append(candidate)
            continue
        if url not in page_cache:
            if len(page_cache) >= 10:
                candidate["still_to_verify"].append("official_page_check_budget_reached")
                pending.append(candidate)
                continue
            page_cache[url] = fetch_official_page_evidence(
                original, active_ids=active_ids, today=today,
            )
        page = page_cache[url]
        candidate["official_page_status"] = page["status"]
        candidate["official_page_language"] = page["page_language"]
        candidate["application_language"] = page["application_language"]
        candidate["application_page_language"] = page.get("application_page_language")
        candidate["application_form_detected"] = page.get("application_form_detected") is True
        structured = page.get("structured")
        if structured is not None:
            candidate["official_structured_date"] = structured.get("date_posted")
            candidate["official_structured_remote"] = structured.get("remote_signal")
            candidate["official_applicant_locations"] = structured.get("applicant_locations")
        reason = _official_page_exclusion(page, policy, today)
        if reason is not None:
            exclusions[reason] += 1
            continue
        missing = _missing_ranking_evidence(candidate, page, policy, today)
        candidate["assessment_context"] = assessment_context(
            original, page, config, tables["CandidateEvidence"],
        )
        decision = validate_assessment(
            original, candidate, page, assessments.get(url), config=config,
            evidence=tables["CandidateEvidence"], policy=policy, today=today,
            missing=missing, active_ids=active_ids,
        )
        if decision["status"] == "verified":
            verified.append(decision["engine_input"])
        elif decision["status"] == "ineligible":
            exclusions["verified_mandatory_requirement_mismatch"] += 1
        else:
            candidate["still_to_verify"] = decision["missing"]
            pending.append(candidate)
    # Existing anchors, weights, threshold boundaries and sorting stay intact.
    final = rank_fully_verified(verified, policy=policy, today=today)
    exclusions["verified_below_live_thresholds"] = sum(
        not rank_fully_verified([item], policy=policy, today=today) for item in verified
    )
    for item in final:
        item["score_breakdown"] = {
            key: item[key] for key in ("core_fit", "evidence_fit", "workstyle_fit")
        }
        item["score_breakdown"]["recency"] = item["score"] - sum(item["score_breakdown"].values())
    return {
        "raw_observations": len(observations), "review_count": len(pending),
        "official_pages_checked": len(page_cache), "preflight_counts": counts,
        "official_exclusion_counts": exclusions, "review_candidates": pending,
        "final_recommendations": final,
        "reason_no_final_recommendations": (
            None if final else "No new vacancy has complete current employer and candidate evidence above the live thresholds."
        ),
    }


def run_once(tables: dict[str, list[dict[str, str]]], root: Path, mode: str,
             *, today: date | None = None, max_free_sources: int = 20,
             verified_assessments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if mode not in GOOGLE_MODES:
        raise ValueError("Unsupported safe search mode")
    today = today or datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    config, policy = live_policy(tables)
    active_ids = {row["source_id"] for row in active_source_rows_from_values([
        ["source_id", "status"],
        *[[row["source_id"], row["status"]] for row in tables["Bronnen"]],
    ])}
    # This argument comes only from the owning workflow's explicit private
    # file; never copy an assessment from a feed, web page or observation.
    review_inputs = verified_assessments if verified_assessments is not None else []
    if not isinstance(review_inputs, list) or len(review_inputs) > 100:
        raise ValueError("Invalid specialist assessment collection")
    assessments: dict[str, dict[str, Any]] = {}
    for review in review_inputs:
        if (not isinstance(review, dict) or not isinstance(review.get("canonical_url"), str)
                or review["canonical_url"] in assessments):
            raise ValueError("Invalid or duplicate specialist assessment")
        assessments[review["canonical_url"]] = review
    google_list = json.loads((root / "ingestion/source-specs.google-optional.json").read_text(encoding="utf-8"))
    deploy_list = json.loads((root / "ingestion/source-specs.deploy.json").read_text(encoding="utf-8"))
    google_approved, _ = filter_source_specs(google_list, active_ids)
    batches = plan_free_source_batches(deploy_list, tables, config, max_sources=max_free_sources)
    pages = GOOGLE_MODES[mode]
    google_status = "not_registered"
    google_observations: list[dict[str, Any]] = []
    google_attempts: list[dict[str, Any]] = []
    if len(google_approved) == 1 and google_approved[0].get("source_id") == "google-jobs":
        google_spec = SourceSpec.from_dict(google_approved[0])
        google_status = google_free_gate(google_spec, pages)
    else:
        google_spec = None
    if not pages:
        return {"mode": mode, "google": google_status,
                "fallback_sources_available": sum(len(b) for b in batches),
                "search_requests": 0, "read_only": True, "source_attempts": []}
    page_cache: dict[str, dict[str, Any]] = {}
    def evaluate(items):
        return evaluate_observations(
            items, tables, config, policy, today=today,
            assessments=assessments, page_cache=page_cache,
        )
    with tempfile.TemporaryDirectory() as temp:
        runner = IngestionRunner(Path(temp) / "observations.sqlite3")
        try:
            if google_status == "ready" and google_spec is not None:
                options = dict(google_spec.options)
                options.update({"max_pages": pages, "max_requests_per_run":
                                pages * len(set(options.get("queries", []))), "free_quota_reserve": 10})
                requested = replace(google_spec, options=options)
                google_result = runner.run_source(requested)
                google_attempts.append(_source_attempt_audit(google_result))
                if google_result.success:
                    google_observations = google_result.observations or []
                    google_status = "searched"
                else:
                    google_status = "provider_unavailable_or_quota_blocked"
            loop = run_free_discovery_batches(
                runner, batches, initial_observations=google_observations,
                evaluate=evaluate, target_verified=policy.max_output_roles,
            )
        finally:
            runner.close()
    audit_report = {
        "mode": mode, "read_only": True, "google": google_status,
        "google_observations": len(google_observations),
        **{k: loop[k] for k in ("fallback_sources_attempted", "fallback_sources_successful",
                               "fallback_batches_completed", "fallback_stop_reason")},
        "source_attempts": google_attempts + loop["source_attempts"],
    }
    if (not any(attempt["success"] for attempt in google_attempts)
            and not loop["fallback_sources_successful"]):
        raise DiscoveryUnavailableError({
            **audit_report, "status": "blocked",
            "blocked_reason": "discovery_sources_unavailable",
        })
    return {
        **loop["evaluation"],
        **audit_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe on-demand Google + existing free ATS/feeds review")
    parser.add_argument("--mode", choices=sorted(GOOGLE_MODES), default="check")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--max-free-sources", type=int, default=20)
    parser.add_argument("--verified-assessments", type=Path,
                        help="Private vacature-search evidence handoff; never feed-provided JSON")
    args = parser.parse_args()
    if args.max_free_sources not in range(1, 21):
        parser.error("--max-free-sources must be between 1 and 20")
    try:
        tables = load_register()
        assessments = None
        if args.verified_assessments is not None:
            if args.verified_assessments.stat().st_size > 2_000_000:
                raise ValueError("Specialist assessment file exceeds size limit")
            assessments = json.loads(args.verified_assessments.read_text(encoding="utf-8"))
        report = run_once(tables, args.root, args.mode, max_free_sources=args.max_free_sources,
                          verified_assessments=assessments)
    except DiscoveryUnavailableError as exc:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(exc.report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("BLOCKED: discovery sources unavailable or unsafe")
        return 2
    except (RegisterPreflightError, ValueError) as exc:
        # No private data, credentials or Register row contents go into logs.
        print("BLOCKED:", type(exc).__name__)
        return 2
    except Exception:
        print("BLOCKED: discovery sources unavailable or unsafe")
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items()
                      if key not in {"review_candidates", "preflight_counts"}},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
