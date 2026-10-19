"""Conservative, evidence-based review of live official ATS observations.

Pure functions: no network, credentials, application submissions or Register writes.
Direct ATS runs are current official listings. Boards, snippets and search hits
NEVER become official evidence merely because their URLs look job-specific.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from vacature_engine.simple import VacancyPolicy, top_vacancies
from .official_page import verified_source_account
_SUPPORTED_EVIDENCE = {"canonical_cv", "github", "user_confirmed", "library_portfolio_master"}
_CORE_TERMS: dict[str, tuple[str, ...]] = {
    "wordpress_ecosystem": ("wordpress", "woocommerce", "elementor", "gutenberg",
                            "plugin development", "plugin developer"),
    "web_design_development": ("web design", "web development", "front-end",
                               "frontend", "ui/ux", "ux/ui", "accessibility"),
    "ai_workflow_automation": ("workflow automation", "ai automation", "automation engineer",
                               "ai agents", "ai agent", "n8n", "orchestration"),
}
_NL_RE = re.compile(r"\b(?:netherlands|nederland|european union|europe|e\.u\.|eu|worldwide|globally|anywhere)\b", re.I)
_EXCLUDED_NL = re.compile(
    r"\b(?:excluding|excluded|except|not available in|not hiring (?:in|from)|"
    r"no applicants from|cannot work from|outside)\s+(?:the\s+)?"
    r"(?:netherlands|nederland|european union|europe|e\.u\.|eu)\b",
    re.I,
)
_BLOCKED_REGIONS = re.compile(
    r"\b(?:united states|usa|u\.s\.a\.|us only|canada|india|costa rica|latam|latin america|"
    r"brazil|mexico|philippines|south africa|australia|uk only|united kingdom)\b", re.I
)
_ONSITE = re.compile(r"\b(?:on.?site|in.?office|office only|hybrid)\b", re.I)
_REMOTE = re.compile(r"\b(?:remote|work from home|distributed)\b", re.I)


def geography_signal(value: Any) -> str:
    """Location-only geography: an unspecified 'remote' is NOT worldwide."""
    if not isinstance(value, str):
        return "unknown"
    location = value.strip().casefold()
    if not location:
        return "unknown"
    # "Worldwide except Netherlands" cannot be marked Netherlands-safe just
    # because the positive word "worldwide" is present.
    if _EXCLUDED_NL.search(location):
        return "restricted"
    if _NL_RE.search(location):
        return "allowed"
    if _BLOCKED_REGIONS.search(location):
        return "restricted"
    return "unknown"


def _source_is_current_official(row: dict[str, Any], active_ids: set[str]) -> bool:
    # Reuse the exact provider + tenant + role URL identity gate used by
    # first-party page fetches. A familiar ATS hostname alone is not proof.
    return verified_source_account(row, active_ids=active_ids) is not None


def _strong_evidence_count(rows: list[dict[str, str]], families: list[str]) -> int:
    """Count only active, source-backed claims matching a relevant technical skill."""
    keywords = {term for family in families for term in _CORE_TERMS.get(family, ())}
    matched_ids: set[str] = set()
    for row in rows:
        if row.get("active", "").casefold() != "true":
            continue
        if row.get("source_type") not in _SUPPORTED_EVIDENCE:
            continue
        if row.get("confidence", "").casefold() not in {"high", "medium"}:
            continue
        claim = row.get("claim", "").casefold()
        if any(term in claim for term in keywords) and row.get("evidence_id"):
            matched_ids.add(row["evidence_id"])
    return len(matched_ids)


def assess_official_observation(
    row: dict[str, Any], *,
    candidate: dict[str, Any],
    active_ids: set[str],
    evidence: list[dict[str, str]],
    policy: VacancyPolicy,
    today: date,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return sanitised verification signals and an optional ranked-engine input.

    Inferences about language or Netherlands eligibility are deliberately
    prohibited. No verified output without ALL authoritative hard gates.
    """
    status: dict[str, Any] = {
        "official_role": "unverified",
        "role_open": "unknown",
        "remote": "unknown",
        "netherlands": "unknown",
        "original_publication": "unknown",
        "language": "unknown",
        "fit_evidence": "unknown",
    }
    if not _source_is_current_official(row, active_ids):
        return status, None

    status["official_role"] = "confirmed_current_public_ats"
    status["role_open"] = "present_in_live_official_feed"
    loc = row.get("location")
    geo = geography_signal(loc)
    status["netherlands"] = geo
    remote = row.get("remote")
    workplace = str(row.get("workplace_type") or "")
    if remote is True or workplace.casefold() == "remote":
        status["remote"] = "confirmed"
    elif remote is False or _ONSITE.search(workplace) or _ONSITE.search(loc or ""):
        status["remote"] = "not_remote"
    elif _REMOTE.search(loc or ""):
        status["remote"] = "needs_structured_confirmation"
    else:
        status["remote"] = "unknown"

    posted = row.get("published_at")
    if isinstance(posted, str) and len(posted) >= 10:
        try:
            age = (today - date.fromisoformat(posted[:10])).days
        except ValueError:
            age = None
        if age is not None:
            # ATS published_at may be the LAST publish/republish date (Ashby
            # documents this explicitly), not the ORIGINAL date required by
            # live policy. Only use it to rule out definitely old jobs.
            if age < 0:
                status["original_publication"] = "future_publication_invalid"
            elif policy.max_posting_age_days and age > policy.max_posting_age_days:
                status["original_publication"] = "too_old"
            # A recent republish is not evidence of a recent original date.
    lang = row.get("listing_language")
    if isinstance(lang, str) and lang.casefold() in {"en", "nl"}:
        status["language"] = "listed_language_supported_application_unverified"

    families = candidate.get("role_family_hints") or []
    supports = _strong_evidence_count(evidence, families)
    status["fit_evidence"] = "supported_claims_available" if supports else "unverified"
    status["evidence_claims_count"] = supports

    # Do not infer application language, required languages, or the exact
    # candidate-job semantic fit from a listing or a keyword match. A genuine
    # recommendation must pass the existing complete deterministic engine.
    # Until employer application-language and other hard gates are verified,
    # preserve the result as unverified; do not fabricate score anchors.
    return status, None


def rank_fully_verified(
    verified_inputs: list[dict[str, Any]],
    *,
    policy: VacancyPolicy,
    today: date,
) -> list[dict[str, Any]]:
    """Reuse the existing central ranking engine; never invent an AI score."""
    return top_vacancies(verified_inputs, policy=policy, today=today)
