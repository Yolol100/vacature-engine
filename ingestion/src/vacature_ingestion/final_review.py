"""Validate the specialist's evidence handoff before the existing engine ranks.

This module never performs semantic assessment or invents score anchors. The
owning vacature-search workflow supplies a private, explicitly selected review
file after reading the employer and CandidateEvidence sources. Feed content can
never supply this handoff. Digests bind it to today's exact policy, evidence,
role and inspected page; changed or missing proof returns to review.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit

from vacature_engine.simple import (
    CORE_FIT_ANCHORS, EVIDENCE_FIT_ANCHORS, WORKSTYLE_FIT_ANCHORS,
    VacancyPolicy, eligibility,
)
from .official_page import verified_source_account
from .requirement_match import has_positive_requirement_claim, valid_library_cv_source
from .adapters.serpapi_google import _safe_candidate_url
from .official_review import geography_signal

REVIEW_DIMENSIONS = frozenset({
    "skills", "experience", "languages", "projects", "responsibilities", "workstyle",
})
_SOURCES = {"canonical_cv", "library_cv", "github", "user_confirmed", "library_portfolio_master"}
_ROLE_FIELDS = (
    "canonical_url", "source_id", "source_instance", "source_job_id", "title",
    "employer", "description", "location", "remote", "published_at", "apply_url",
    "listing_language", "workplace_type", "valid_through", "source_metadata",
)
_PAGE_FIELDS = (
    "status", "job_http_status", "apply_http_status", "page_language", "application_language",
    "application_page_language", "application_form_detected", "structured",
    "visible_text", "application_visible_text",
)


def proof_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def assessment_context(row: dict[str, Any], page: dict[str, Any],
                       config: dict[str, str], evidence: list[dict[str, str]]) -> dict[str, str]:
    """Stable inputs for a private handoff; no claims or evidence IDs exported."""
    return {
        "policy_sha256": proof_digest(config),
        "candidate_evidence_sha256": proof_digest(sorted(evidence, key=proof_digest)),
        "observation_sha256": proof_digest({k: row.get(k) for k in _ROLE_FIELDS}),
        # Nonces and hidden anti-CSRF tokens may change on every legitimate
        # fetch. Bind semantic page evidence, not unrelated HTML bytes.
        "official_page_sha256": proof_digest({k: page.get(k) for k in _PAGE_FIELDS}),
    }


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _public_url(value: Any) -> bool:
    return _safe_candidate_url(value) is not None


def _verified_evidence(rows: list[dict[str, str]], today: date,
                       config: dict[str, str]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    duplicate_ids: set[str] = set()
    seen_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        identity = row.get("evidence_id", "")
        if not isinstance(identity, str) or not identity:
            continue
        if identity in seen_ids:
            duplicate_ids.add(identity)
        seen_ids.add(identity)
        try:
            raw_date = row.get("verified_at", "")
            if not isinstance(raw_date, str):
                continue
            raw_date = raw_date.strip()
            if len(raw_date) == 10:
                verified = date.fromisoformat(raw_date)
            elif len(raw_date) > 10 and raw_date[10] in {"T", " "}:
                verified = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
            else:
                continue
        except (ValueError, TypeError):
            continue
        if (str(row.get("active", "")).casefold() != "true"
                or not isinstance(row.get("source_type"), str) or row.get("source_type") not in _SOURCES
                or str(row.get("confidence", "")).casefold() not in {"high", "medium"}
                or not identity or verified > today
                or not _text(row.get("source_ref")) or not _text(row.get("source_locator"))
                or not valid_library_cv_source(row)
                # A canonical CV claim must match the live configured ID;
                # a stale 404 pointer never establishes provenance.
                or (row.get("source_type") == "canonical_cv"
                    and row.get("source_ref") != config.get("canonical_cv_file_id"))
                or not has_positive_requirement_claim(row.get("claim"))):
            continue
        index[identity] = row
    for identity in duplicate_ids:
        index.pop(identity, None)
    return index


def automated_ranking_blockers(candidate: dict[str, Any], page: dict[str, Any],
                              policy: VacancyPolicy, today: date) -> list[str]:
    """Non-overridable machine checks plus the specialist-owned proof gates."""
    missing: list[str] = []
    checks = candidate.get("official_checks") or {}
    if checks.get("official_role") != "confirmed_current_public_ats":
        missing.append("official_employer_and_exact_role")
    if page.get("status") != "matching_first_party_jobposting":
        missing.append("matching_visible_first_party_job_page")
    info = page.get("structured")
    info = info if isinstance(info, dict) else {}
    posted = info.get("date_posted")
    try:
        parsed_date = date.fromisoformat(posted) if isinstance(posted, str) else None
    except ValueError:
        parsed_date = None
    if info.get("date_posted_valid") is not True or parsed_date is None:
        missing.append("original_publication_date")
    else:
        age = (today - parsed_date).days
        if age < 0 or policy.max_posting_age_days > 0 and age > policy.max_posting_age_days:
            missing.append("valid_original_publication_date")
    if info.get("expired_by_valid_through") is True:
        missing.append("unexpired_official_role")
    if checks.get("remote") != "confirmed" or info.get("remote_signal") is not True:
        missing.append("fully_remote_from_first_party")
    locations = info.get("applicant_locations")
    if (checks.get("netherlands") != "allowed" or not isinstance(locations, list)
            or not all(isinstance(x, str) for x in locations)
            or geography_signal(", ".join(locations)) != "allowed"):
        missing.append("netherlands_executable_from_employer")
    if page.get("apply_http_status") != 200 or page.get("application_form_detected") is not True:
        missing.append("verified_application_form_at_exact_route")
    if policy.allowed_listing_languages is not None:
        if page.get("page_language") not in policy.allowed_listing_languages:
            missing.append("verified_listing_language")
        if page.get("application_language") not in policy.allowed_listing_languages:
            missing.append("employer_authorized_application_language")
        missing.append("employer_required_work_languages")
    coverage = candidate.get("technical_requirement_review") or {}
    if (coverage.get("status") != "mapped_skills_have_evidence"
            or coverage.get("explicit_technical_requirements", 0) < 1):
        missing.append("complete_candidate_requirement_evidence")
    missing.append("verified_core_duties_and_score_anchors")
    return missing


def validate_assessment(
    row: dict[str, Any], candidate: dict[str, Any], page: dict[str, Any],
    assessment: Any, *, config: dict[str, str], evidence: list[dict[str, str]],
    policy: VacancyPolicy, today: date, missing: list[str], active_ids: set[str],
) -> dict[str, Any]:
    """Return pending/ineligible/verified; only verified has engine_input.

    Requirements and score rationales are private. Public output contains
    requirement counts, source URLs and proof digests only. Absence of candidate
    evidence cannot establish a negative requirement outcome either.
    """
    pending = list(dict.fromkeys([*missing, *automated_ranking_blockers(candidate, page, policy, today)]))
    result: dict[str, Any] = {"status": "pending", "missing": pending, "engine_input": None}
    if not isinstance(assessment, dict):
        pending.append("specialist_evidence_assessment")
        return result
    if (type(assessment.get("schema_version")) is not int or assessment.get("schema_version") != 1
            or assessment.get("reviewer") != "vacature-search"
            or assessment.get("reviewed_on") != today.isoformat()
            or assessment.get("canonical_url") != row.get("canonical_url")):
        pending.append("current_exact_role_assessment")
        return result
    context = assessment_context(row, page, config, evidence)
    if any(assessment.get(k) != v for k, v in context.items()):
        pending.append("assessment_inputs_changed")
        return result
    if verified_source_account(row, active_ids=active_ids) is None:
        pending.append("register_approved_official_ats_identity")
        return result

    # An independent employer/ATS ownership read remains the specialist's job.
    # An ATS tenant name, search result or JobPosting script cannot attest to it.
    employer = assessment.get("employer_verification")
    if (not isinstance(employer, dict) or employer.get("status") != "verified"
            or employer.get("checked_on") != today.isoformat()
            or not _public_url(employer.get("employer_url"))
            or employer.get("official_role_url") != row.get("canonical_url")
            or not _text(employer.get("ownership_evidence"))
            or urlsplit(employer["employer_url"]).hostname
            == urlsplit(row["canonical_url"]).hostname):
        pending.append("independent_employer_and_ats_ownership_evidence")
        return result

    visible = _text(page.get("visible_text"))
    application_visible = _text(page.get("application_visible_text"))
    facts = assessment.get("facts")
    if not isinstance(facts, dict):
        pending.append("visible_employer_facts")
        return result
    for key in ("fully_remote", "netherlands_execution", "original_publication",
                "application_language", "required_languages"):
        fact = facts.get(key)
        allowed_text = visible + " " + application_visible if key == "application_language" else visible
        if (not isinstance(fact, dict) or len(_text(fact.get("quote"))) < 5
                or _text(fact.get("quote")) not in allowed_text):
            pending.append("visible_employer_fact:" + key)
    if any(p.startswith("visible_employer_fact:") for p in pending):
        return result
    info = page.get("structured") or {}
    if (facts["fully_remote"].get("value") is not True
            or facts["netherlands_execution"].get("value") is not True):
        pending.append("employer_remote_and_netherlands_confirmation")
        return result
    if facts["original_publication"].get("value") != info.get("date_posted"):
        pending.append("consistent_original_publication_date")
        return result
    application_language = facts["application_language"].get("value")
    languages = facts["required_languages"].get("value")
    if (not isinstance(languages, list) or not all(isinstance(x, str) for x in languages)
            or len(set(languages)) != len(languages)
            or not isinstance(application_language, str)
            or application_language not in (policy.allowed_listing_languages or set())
            or set(languages) - (policy.allowed_listing_languages or set())):
        pending.append("allowed_employer_languages")
        return result

    if (assessment.get("requirements_complete") is not True
            or not isinstance(assessment.get("reviewed_dimensions"), list)
            or not all(isinstance(x, str) for x in assessment["reviewed_dimensions"])
            or set(assessment["reviewed_dimensions"]) != REVIEW_DIMENSIONS):
        pending.append("all_requirement_dimensions_reviewed")
        return result
    requirements = assessment.get("requirements")
    if not isinstance(requirements, list) or not 1 <= len(requirements) <= 100:
        pending.append("complete_requirement_matrix")
        return result
    evidence_index = _verified_evidence(evidence, today, config)
    requirement_index: dict[str, dict[str, Any]] = {}
    languages_reviewed: set[str] = set()
    negative: list[str] = []
    public_description = visible + " " + _text(row.get("description"))
    for req in requirements:
        if (not isinstance(req, dict) or not isinstance(req.get("id"), str)
                or not req["id"] or req["id"] in requirement_index
                or not isinstance(req.get("kind"), str) or req.get("kind") not in REVIEW_DIMENSIONS
                or type(req.get("mandatory")) is not bool
                or not isinstance(req.get("outcome"), str)
                or req.get("outcome") not in {"met", "not_met", "unknown"}
                or len(_text(req.get("quote"))) < 5
                or _text(req["quote"]) not in public_description):
            pending.append("valid_requirement_matrix")
            continue
        requirement_index[req["id"]] = req
        refs = req.get("candidate_evidence", [])
        supported = isinstance(refs, list) and bool(refs)
        for ref in refs if isinstance(refs, list) else []:
            live = (evidence_index.get(ref["evidence_id"])
                    if isinstance(ref, dict) and isinstance(ref.get("evidence_id"), str) else None)
            if (live is None or ref.get("claim_sha256") != proof_digest(live["claim"])
                    or ref.get("source_ref") != live["source_ref"]
                    or ref.get("source_status") != "verified"
                    or ref.get("source_checked_on") != today.isoformat()):
                supported = False
        if req["outcome"] != "unknown" and (not supported or not _text(req.get("rationale"))):
            pending.append("verified_candidate_requirement_evidence")
        if req["mandatory"]:
            if req["outcome"] == "unknown":
                pending.append("mandatory_requirement_unknown")
            elif req["outcome"] == "not_met" and supported:
                negative.append(req["id"])
        if req["kind"] == "languages" and req["mandatory"] and req["outcome"] == "met":
            if isinstance(req.get("language"), str):
                languages_reviewed.add(req["language"])
    if set(languages) != languages_reviewed:
        pending.append("candidate_required_language_evidence")

    anchors = assessment.get("anchors")
    values: dict[str, float] = {}
    for key, allowed, dimensions in (
        ("core_fit", CORE_FIT_ANCHORS, {"skills", "responsibilities"}),
        ("evidence_fit", EVIDENCE_FIT_ANCHORS, {"skills", "projects", "experience"}),
        ("workstyle_fit", WORKSTYLE_FIT_ANCHORS, {"workstyle", "responsibilities"}),
    ):
        anchor = anchors.get(key) if isinstance(anchors, dict) else None
        if not isinstance(anchor, dict):
            pending.append("verified_anchor:" + key)
            continue
        value, refs = anchor.get("value"), anchor.get("requirement_ids")
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or value not in allowed or not _text(anchor.get("rationale"))
                or not isinstance(refs, list) or not refs
                or any(not isinstance(r, str) or r not in requirement_index for r in refs)):
            pending.append("verified_anchor:" + key)
            continue
        if (any(requirement_index[r]["outcome"] != "met" for r in refs)
                or not any(requirement_index[r]["kind"] in dimensions for r in refs)):
            pending.append("verified_anchor:" + key)
            continue
        values[key] = value

    # Remove only specialist-owned blockers after their entire handoff passes.
    owned = {"employer_authorized_application_language", "employer_required_work_languages",
             "complete_candidate_requirement_evidence", "verified_core_duties_and_score_anchors"}
    unresolved = list(dict.fromkeys(p for p in pending if p not in owned))
    result["missing"] = unresolved
    if unresolved:
        return result
    if negative:
        result.update(status="ineligible", reasons=["verified_mandatory_requirement_mismatch"])
        return result
    families = assessment.get("role_families")
    if (not isinstance(families, list) or not families
            or any(not isinstance(x, str) for x in families)
            or not set(families).issubset(set(candidate.get("role_family_hints") or []))):
        result["missing"] = ["verified_material_role_family"]
        return result
    normalized = {
        "title": row["title"], "employer": row["employer"],
        "canonical_url": row["canonical_url"], "posted_date": info.get("date_posted"),
        "fully_remote": True, "geography_compatible": True, "role_families": families,
        "central_hard_mismatch": False, "listing_language": page.get("page_language"),
        "application_language": application_language, "required_languages": languages,
        "authenticity": "verified", "role_open": True, **values,
        # Salary stays unknown: no inference or currency/unit conversion.
        "salary_monthly_eur": None,
        "verification": {"assessment_sha256": proof_digest(assessment), **context,
                         "reviewed_on": today.isoformat(), "requirements": len(requirements),
                         "mandatory_requirements": sum(r["mandatory"] for r in requirements),
                         "employer_url": employer["employer_url"]},
    }
    gate = eligibility(normalized, today=today, policy=policy)
    if not gate["pass"]:
        result.update(status="ineligible", reasons=gate["reasons"])
        return result
    result.update(status="verified", missing=[], engine_input=normalized)
    return result
