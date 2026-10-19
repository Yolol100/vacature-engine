"""One on-demand, read-only vacancy discovery and history preflight.

Google is optional and must be verified free. Existing active public ATS/feeds
continue when the Google key, quota or research provider is unavailable.
This is a REVIEW QUEUE, not a verified recommendation or an application.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from vacature_engine.observations import canonicalize_observations, is_role_specific_vacancy_url
from vacature_engine.simple import VacancyPolicy, policy_from_config
from vacature_ingestion.adapters.serpapi_google import (
    _ACCOUNT_URL, _get_json, _is_safe_free_account, _safe_candidate_url,
)
from vacature_ingestion.models import SourceSpec
from vacature_ingestion.registry_filter import (
    _request_json, _service_account_token, active_source_rows_from_values,
    filter_source_specs,
)
from vacature_ingestion.runner import IngestionRunner


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
                      config: dict[str, str], limit: int = 8) -> list[SourceSpec]:
    """Keep active Register-approved existing adapters, including genuine feeds."""
    active = active_source_rows_from_values([
        ["source_id", "status"],
        *[[row["source_id"], row["status"]] for row in tables["Bronnen"]],
    ])
    active_ids = {row["source_id"] for row in active}
    approved, _ = filter_source_specs(raw, active_ids)
    sources = {row["source_id"]: row for row in tables["Bronnen"] if row.get("status", "").lower() == "active"}
    order = [part.strip() for part in config.get("direct_discovery_order", "").split(",")]
    priorities = {"high": 0, "medium": 1, "low": 2}
    unique: dict[str, dict[str, Any]] = {}
    for item in approved:
        if item.get("adapter") == "serpapi_google":
            continue
        if item.get("source_type") not in _ATS | _FREE_DISCOVERY:
            continue
        spec = SourceSpec.from_dict(item)
        unique.setdefault(spec.instance_id, item)

    def rank(item: dict[str, Any]) -> tuple[int, int, str]:
        row = sources.get(item["source_id"], {})
        return (order.index(item["source_type"]) if item["source_type"] in order else 999,
                priorities.get(row.get("priority", ""), 3),
                item["source_id"] + ":" + item["account"])

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


def _previous_index(tables: dict[str, list[dict[str, str]]]) -> tuple[set[str], set[tuple[str, str]]]:
    """Honor the live dedupe statuses; never silently promote unreviewed rows."""
    config = {row.get("key"): row.get("value", "") for row in tables["Config"]}
    statuses = {value.strip().casefold() for value in
                config.get("dedupe_previous_statuses", "").split(",") if value.strip()}
    if not statuses:
        raise RegisterPreflightError("Live dedupe status policy is missing")
    prior_ids: set[str] = set()
    urls: set[str] = set()
    weak: set[tuple[str, str]] = set()
    for row in tables["Vacatures"]:
        if row.get("status", "").casefold() not in statuses:
            continue
        if row.get("vacancy_id"):
            prior_ids.add(row["vacancy_id"])
        title = row.get("title", "").strip().casefold()
        employer = row.get("employer", "").strip().casefold()
        if title and employer:
            weak.add((employer, title))
        for column in ("canonical_url", "official_url"):
            url = _safe_candidate_url(row.get(column))
            if url and is_role_specific_vacancy_url(url):
                urls.add(url)
    # Historical snapshots capture previous canonical URLs for the same role.
    for row in tables["JobSnapshots"]:
        # Only historical snapshots tied to a previously reviewed vacancy.
        if row.get("vacancy_id") not in prior_ids:
            continue
        url = _safe_candidate_url(row.get("canonical_url"))
        if url and is_role_specific_vacancy_url(url):
            urls.add(url)
    for row in tables["Applications"]:
        # Submitted/drafted applications also count if their Vacatures row is
        # missing, but only when a strong application link is present.
        url = _safe_candidate_url(row.get("application_url"))
        if url and is_role_specific_vacancy_url(url):
            urls.add(url)
    return urls, weak


def _role_hints(row: dict[str, Any], policy: VacancyPolicy) -> list[str]:
    # Title words are only review hints, NEVER proof of full role eligibility.
    title = str(row.get("title") or "").casefold()
    return [name for name, tokens in _ROLE_TERMS.items()
            if name in policy.target_role_families and any(term in title for term in tokens)]


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
    historical_urls, weak = _previous_index(tables)
    counted = {"previously_registered": 0, "possible_prior_match": 0,
               "explicit_mismatch": 0, "unsafe_link": 0, "awaiting_verification": 0}
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in canonicalize_observations(observations):
        url = _safe_candidate_url(row.get("canonical_url") or row.get("url"))
        if not url or not is_role_specific_vacancy_url(url):
            counted["unsafe_link"] += 1
            continue
        if url in seen:
            continue
        seen.add(url)
        if url in historical_urls:
            counted["previously_registered"] += 1
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
        if (employer.casefold(), title.casefold()) in weak and employer and title:
            counted["possible_prior_match"] += 1
            # A different URL may be the user's previously applied role.
            continue
        if len(output) >= limit:
            break
        # Do not export application states or CandidateEvidence in a public artifact.
        output.append({
            "title": title[:400], "employer": employer[:250] or None,
            "official_role_candidate_url": url,
            "source_types": row.get("source_types") or [row.get("source_type")],
            "role_family_hints": _role_hints(row, policy),
            "status": "unverified_review_only",
            "still_to_verify": [
                "official_employer_and_exact_open_role", "original_publication_date",
                "fully_remote_and_allowed_from_netherlands", "work_and_application_language",
                "candidate_evidence_fit_and_score", "application_route",
            ],
        })
        counted["awaiting_verification"] += 1
    return output, counted


def run_once(tables: dict[str, list[dict[str, str]]], root: Path, mode: str,
             *, today: date | None = None, max_free_sources: int = 8) -> dict[str, Any]:
    if mode not in GOOGLE_MODES:
        raise ValueError("Unsupported safe search mode")
    config, policy = live_policy(tables)
    active_ids = {row["source_id"] for row in active_source_rows_from_values([
        ["source_id", "status"],
        *[[row["source_id"], row["status"]] for row in tables["Bronnen"]],
    ])}
    google_list = json.loads((root / "ingestion/source-specs.google-optional.json").read_text(encoding="utf-8"))
    deploy_list = json.loads((root / "ingestion/source-specs.deploy.json").read_text(encoding="utf-8"))
    google_approved, _ = filter_source_specs(google_list, active_ids)
    free_sources = select_free_specs(deploy_list, tables, config, limit=max_free_sources)

    pages = GOOGLE_MODES[mode]
    google_status = "not_registered"
    google_observations: list[dict[str, Any]] = []
    if len(google_approved) == 1 and google_approved[0].get("source_id") == "google-jobs":
        google_spec = SourceSpec.from_dict(google_approved[0])
        google_status = google_free_gate(google_spec, pages)
    else:
        google_spec = None
    if not pages:
        return {"mode": mode, "google": google_status, "fallback_sources_available": len(free_sources),
                "search_requests": 0, "read_only": True}

    observations: list[dict[str, Any]] = []
    attempts = successes = 0
    # Temporary run state is never the authoritative historical/application store.
    with tempfile.TemporaryDirectory() as temp:
        runner = IngestionRunner(Path(temp) / "observations.sqlite3")
        try:
            if google_status == "ready" and google_spec is not None:
                options = dict(google_spec.options)
                options.update({"max_pages": pages, "max_requests_per_run":
                                pages * len(set(options.get("queries", []))), "free_quota_reserve": 10})
                requested = replace(google_spec, options=options)
                google_result = runner.run_source(requested)
                if google_result.success:
                    google_observations = google_result.observations or []
                    observations.extend(google_observations)
                    google_status = "searched"
                else:
                    google_status = "provider_unavailable_or_quota_blocked"
            # Always keep the original free source route, whether Google works or not.
            for source in free_sources:
                attempts += 1
                result = runner.run_source(source)
                if result.success:
                    successes += 1
                    observations.extend(result.observations or [])
        finally:
            runner.close()
    if not google_observations and not successes:
        raise RuntimeError("No permitted free discovery source succeeded")
    candidates, counts = screen_review_candidates(
        observations, tables, policy, today=today or date.today(),
        limit=max(20, min(100, policy.max_output_roles * 12)),
    )
    return {
        "mode": mode, "read_only": True, "google": google_status,
        "google_observations": len(google_observations),
        "fallback_sources_attempted": attempts, "fallback_sources_successful": successes,
        "raw_observations": len(observations), "review_count": len(candidates),
        "preflight_counts": counts, "review_candidates": candidates,
        "final_recommendations": [],
        "reason_no_final_recommendations": "Official role, NL remote, language and personal evidence must be verified before ranking.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe on-demand Google + existing free ATS/feeds review")
    parser.add_argument("--mode", choices=sorted(GOOGLE_MODES), default="check")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--max-free-sources", type=int, default=8)
    args = parser.parse_args()
    if args.max_free_sources not in range(1, 21):
        parser.error("--max-free-sources must be between 1 and 20")
    try:
        tables = load_register()
        report = run_once(tables, args.root, args.mode, max_free_sources=args.max_free_sources)
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
