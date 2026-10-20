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
from .requirement_match import has_positive_skill_claim, valid_library_cv_source
_SUPPORTED_EVIDENCE = {"canonical_cv", "library_cv", "github", "user_confirmed", "library_portfolio_master"}
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


def discovery_region_conflict(row: dict[str, Any], *, include_ats: bool = False) -> str | None:
    """Negative discovery evidence only; never a verified geographic pass.

    A third-party mistake must not change lifecycle state or establish fraud;
    the observation is merely withheld from the candidate review shortlist.
    Callers may apply this same negative-only check to ATS observations whose
    custom employer URL has not passed the independent official-role gate.
    """
    if row.get("source_type") == "ats" and not include_ats:
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
        if not valid_library_cv_source(row):
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


class _ValidatedRankingInput(dict):
    """Internal in-memory handoff emitted only after validate_assessment passes.

    Parsed JSON/ATS/feed observations are plain dictionaries and cannot enter
    final scoring by copying score fields. This tag is not independent official
    evidence: final_review.validate_assessment still owns every semantic gate.
    """


_RANKING_DIGEST_FIELDS = (
    "assessment_sha256", "policy_sha256", "candidate_evidence_sha256",
    "observation_sha256", "official_page_sha256",
)


def rank_fully_verified(
    verified_inputs: list[dict[str, Any]],
    *,
    policy: VacancyPolicy,
    today: date,
) -> list[dict[str, Any]]:
    """Apply a second *structural* check to validated specialist handoffs.

    Verification is owned by validate_assessment, not by this helper. Keep
    the existing central top_vacancies scores, thresholds and sorting intact.
    A raw score payload, stale handoff or incomplete digest cannot be ranked.
    """
    admitted = []
    for item in verified_inputs:
        if not isinstance(item, _ValidatedRankingInput):
            continue
        if item.get("authenticity") != "verified" or item.get("role_open") is not True:
            continue
        proof = item.get("verification")
        if not isinstance(proof, dict) or proof.get("reviewed_on") != today.isoformat():
            continue
        if any(not isinstance(proof.get(field), str)
               or re.fullmatch(r"[0-9a-f]{64}", proof[field]) is None
               for field in _RANKING_DIGEST_FIELDS):
            continue
        required = proof.get("requirements")
        mandatory = proof.get("mandatory_requirements")
        if (type(required) is not int or not 1 <= required <= 100
                or type(mandatory) is not int or not 0 <= mandatory <= required):
            continue
        admitted.append(item)
    return top_vacancies(admitted, policy=policy, today=today)
