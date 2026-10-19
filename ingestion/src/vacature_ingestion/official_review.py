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
from .requirement_match import has_positive_skill_claim
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
    r"brazil|mexico|colombia|argentina|chile|peru|philippines|"
    r"south africa|australia|uk only|united kingdom)\b", re.I
)
# Narrow negative signals only: board/aggregator copy is never proof that
# a candidate CAN work from the Netherlands. Explicitly excluded foreign
# residency is enough to remove a listing from the provisional NL shortlist.
# Never infer exclusion from "our office is in X" or a company's customers.
_EXCLUSIVE_RESIDENCE = re.compile(
    r"\b(?:exclusively\s+considering|only\s+considering|only\s+accepting|"
    r"exclusively\s+accepting|we\s+only\s+hire|"
    r"applicants?\s+must\s+(?:currently\s+)?(?:be\s+)?(?:based|located|residing)|"
    r"must\s+(?:currently\s+)?(?:be\s+)?(?:based|located|residing))"
    r".{0,150}?\b(?:latam|latin\s+america|philippines|colombia|"
    r"india|costa\s+rica|brazil|mexico|argentina|chile|peru|"
    r"united\s+states|canada|australia)\b",
    re.I | re.S,
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


def discovery_region_conflict(row: dict[str, Any]) -> str | None:
    """Negative discovery evidence only; never a verified geographic pass.

    A third-party mistake must not change lifecycle state or establish fraud;
    the observation is merely withheld from the candidate review shortlist.
    """
    if row.get("source_type") == "ats":
        return None
    metadata = row.get("source_metadata")
    restrictions = (
        metadata.get("location_restriction_names")
        if isinstance(metadata, dict) else None
    )
    if isinstance(restrictions, list) and restrictions and all(
        geography_signal(value) == "restricted" for value in restrictions
    ):
        return "explicit_discovery_region_list"
    location = row.get("location")
    if geography_signal(location) == "restricted":
        return "restricted_discovery_location"
    description = row.get("description")
    if isinstance(description, str) and _EXCLUSIVE_RESIDENCE.search(description[:10_000]):
        # A contradictory broad location label is a reason for human review,
        # not proof that the employer excludes the Netherlands.
        if geography_signal(location) == "allowed":
            return None
        return "explicit_discovery_residency_requirement"
    return None


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
        claim = row.get("claim", "")
        if (has_positive_skill_claim(claim)
                and any(term in claim.casefold() for term in keywords)
                and row.get("evidence_id")):
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


# Required independent specialist conclusions. Every state needs a concrete
# source reference. These are attestations, not a substitute for checking the
# actual employer page or the live Register before making a claim.
_FINAL_GATES = (
    "employer_identity_and_ats",
    "authenticity",
    "exact_official_open_role",
    "fully_remote_from_netherlands",
    "original_posting_date",
    "listing_and_application_languages",
    "required_languages_and_experience_years",
    "mandatory_and_optional_requirements",
    "responsibilities_and_workstyle",
    "candidate_evidence_fit",
    "application_route",
    "new_unseen_unapplied_and_not_rejected",
    "target_family_not_sales_or_management",
)


def _verified_ranking_input(
    item: dict[str, Any],
    active_evidence_ids: set[str],
    prior_role_urls: set[str],
) -> bool:
    """Fail closed on absent evidence; never infer proof from job keywords."""
    from urllib.parse import urlsplit
    from vacature_engine.observations import is_role_specific_vacancy_url

    role_url = item.get("canonical_url")
    official_url = item.get("official_url")
    if not isinstance(role_url, str) or role_url != official_url:
        return False
    try:
        parsed = urlsplit(role_url)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.username or parsed.password
                or parsed.port not in (None, 443)
                or not is_role_specific_vacancy_url(role_url)):
            return False
    except (ValueError, UnicodeError):
        return False
    if role_url in prior_role_urls:
        return False
    if (item.get("central_hard_mismatch") is not False
            or not isinstance(item.get("title"), str)
            or not item["title"].strip()
            or not isinstance(item.get("employer"), str)
            or not item["employer"].strip()):
        return False

    gates = item.get("verification")
    if not isinstance(gates, dict):
        return False
    for gate in _FINAL_GATES:
        proof = gates.get(gate)
        if (not isinstance(proof, dict)
                or proof.get("state") != "verified"
                or not isinstance(proof.get("source_ref"), str)
                or not proof["source_ref"].strip()):
            return False
    if gates["exact_official_open_role"]["source_ref"] != role_url:
        return False
    if gates["original_posting_date"].get("date") != item.get("posted_date"):
        return False
    try:
        date.fromisoformat(item["posted_date"])
    except (TypeError, ValueError):
        return False

    # The caller supplies this set only after reading ACTIVE, source-backed
    # high/medium-confidence rows from the live CandidateEvidence sheet.
    evidence_ids = item.get("candidate_evidence_ids")
    if (not isinstance(evidence_ids, list) or not evidence_ids
            or any(not isinstance(value, str) or value not in active_evidence_ids
                   for value in evidence_ids)):
        return False
    anchors = item.get("anchor_provenance")
    if not isinstance(anchors, dict):
        return False
    if any(not isinstance(anchors.get(part), list) or not anchors[part]
           or any(not isinstance(ref, str) or not ref.strip() for ref in anchors[part])
           for part in ("core_fit", "evidence_fit", "workstyle_fit")):
        return False
    if (role_url not in anchors["core_fit"]
            or not set(evidence_ids).intersection(anchors["evidence_fit"])
            or not set(evidence_ids).intersection(anchors["workstyle_fit"])):
        return False
    return True


def rank_fully_verified(
    verified_inputs: list[dict[str, Any]],
    *,
    policy: VacancyPolicy,
    today: date,
    active_evidence_ids: set[str] | None = None,
    prior_role_urls: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Score only independently verified, new roles with live evidence refs.

    This final admission gate intentionally does not change top_vacancies or
    its existing 30-case benchmark and weights. Semantic evidence and proof
    states must be supplied by vacature-search after official and Register
    checks. No proof or missing live history => no final score.
    """
    if not isinstance(active_evidence_ids, set) or not isinstance(prior_role_urls, set):
        return []
    eligible = []
    for item in verified_inputs:
        if not isinstance(item, dict):
            continue
        if _verified_ranking_input(item, active_evidence_ids, prior_role_urls):
            # Keep private evidence IDs and verification envelopes out of the
            # returned shortlist; only the deterministic engine output remains.
            eligible.append({
                key: value for key, value in item.items()
                if key not in {"verification", "candidate_evidence_ids", "anchor_provenance"}
            })
    return top_vacancies(eligible, policy=policy, today=today)
