from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urlsplit

LOGIC_VERSION = "2026-08-25-v3"

MATCH_COMPONENTS = {
    "hard_requirements": 35,
    "experience_seniority": 20,
    "cv_portfolio_evidence": 15,
    "wordpress_stack": 10,
    "quality_stack": 10,
    "communication_autonomy": 5,
    "preferred_requirements": 5,
}
OPPORTUNITY_COMPONENTS = {
    "freshness": 15,
    "competition": 10,
    "netherlands_certainty": 10,
    "employer_credibility": 5,
    "compensation_contract_fit": 5,
}

_SENIORITY_ALLOWED = (
    "medior",
    "mid-level",
    "mid level",
    "senior",
    "specialist",
    "autonomous",
    "lead",
    "principal",
    "staff",
    "expert",
    "consultant",
)
_SENIORITY_BLOCKED = (
    "junior",
    "intern",
    "internship",
    "trainee",
    "graduate",
    "entry-level",
    "entry level",
    "apprentice",
)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _strict_optional_bool(data: dict[str, Any], key: str) -> bool:
    value = data.get(key, False)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean")
    return value


def hard_gate(data: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    age = _finite_number(data.get("posted_age_days"))
    if age is None or age < 0 or age > 7:
        reasons.append("posting_age_not_within_7_days")
    if data.get("active") is not True:
        reasons.append("official_posting_not_confirmed_active")
    if data.get("official_link_working") is not True:
        reasons.append("official_link_not_confirmed_working")
    if data.get("fully_remote") is not True:
        reasons.append("not_confirmed_fully_remote")
    if data.get("netherlands_eligibility") not in {"allowed", "plausible"}:
        reasons.append("netherlands_eligibility_not_sufficiently_supported")

    for key, reason in {
        "mandatory_relocation": "mandatory_relocation",
        "structural_office_attendance": "structural_office_attendance",
        "unpaid_test": "mandatory_unpaid_test",
        "commission_only": "commission_only",
        "suspicious_payment": "suspicious_payment_terms",
        "marketplace_excluded": "excluded_marketplace_or_paywall",
        "duplicate": "duplicate_or_previously_shown",
        "us_residents_only": "us_residents_only",
    }.items():
        value = data.get(key, False)
        if not isinstance(value, bool):
            reasons.append(f"invalid_{key}")
        elif value:
            reasons.append(reason)

    level = str(data.get("level", "")).strip().lower()
    if any(term in level for term in _SENIORITY_BLOCKED):
        reasons.append("level_below_required_seniority")
    elif not level or not any(term in level for term in _SENIORITY_ALLOWED):
        reasons.append("level_not_confirmed_medior_or_above")

    mismatch_count = data.get("central_hard_mismatch_count", 0)
    if isinstance(mismatch_count, bool) or not isinstance(mismatch_count, int) or mismatch_count < 0:
        reasons.append("invalid_central_hard_mismatch_count")
    elif mismatch_count > 0:
        reasons.append("central_hard_requirement_mismatch")
    return {"pass": not reasons, "reasons": reasons}


def _bounded(data: dict[str, Any], key: str, maximum: float) -> float:
    value = _finite_number(data.get(key))
    if value is None:
        raise ValueError(f"{key} must be a finite number")
    if value < 0 or value > maximum:
        raise ValueError(f"{key} must be between 0 and {maximum}")
    return value


def score(data: dict[str, Any]) -> dict[str, Any]:
    match_parts = {key: _bounded(data, key, maximum) for key, maximum in MATCH_COMPONENTS.items()}
    raw_match = sum(match_parts.values())
    multiple = _strict_optional_bool(data, "multiple_central_hard_mismatches")
    central_missing = _strict_optional_bool(data, "central_hard_missing")
    match_score = min(raw_match, 59.0) if central_missing else raw_match
    opportunity_parts = {
        key: _bounded(data, key, maximum) for key, maximum in OPPORTUNITY_COMPONENTS.items()
    }
    match_contribution = match_score * 0.55
    return {
        "logic_version": LOGIC_VERSION,
        "excluded": multiple,
        "exclusion_reason": "multiple_central_hard_mismatches" if multiple else None,
        "match_components": match_parts,
        "raw_match_score": round(raw_match, 1),
        "match_score": round(match_score, 1),
        "opportunity_components": {
            "match_contribution": round(match_contribution, 1),
            **opportunity_parts,
        },
        "opportunity_score": round(match_contribution + sum(opportunity_parts.values()), 1),
    }


def _valid_https_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
        return parts.scheme == "https" and bool(parts.hostname) and parts.username is None and parts.password is None
    except ValueError:
        return False


def application_guard(data: dict[str, Any]) -> dict[str, Any]:
    stage = data.get("stage")
    if stage not in {"prepare", "draft"}:
        raise ValueError("stage must be prepare or draft")
    reasons: list[str] = []
    if data.get("user_explicitly_requested") is not True:
        reasons.append("user_request_missing")
    if data.get("final_verification_pass") is not True:
        reasons.append("vacancy_final_verification_not_passed")
    if data.get("hard_gate_pass") is not True:
        reasons.append("vacancy_hard_gate_not_passed")
    if data.get("cv_selected") is not True:
        reasons.append("cv_not_selected")

    if stage == "draft":
        email = str(data.get("recipient_email", "")).strip()
        source = str(data.get("recipient_source_url", "")).strip()
        if (
            data.get("recipient_verified") is not True
            or data.get("recipient_authorized_for_role") is not True
            or not _EMAIL_RE.fullmatch(email)
            or not _valid_https_url(source)
        ):
            reasons.append("verified_role_application_recipient_missing")
        if data.get("factual_qa") != "pass":
            reasons.append("factual_qa_not_passed")
        if data.get("style_qa") != "pass":
            reasons.append("style_qa_not_passed")
        if data.get("cv_attachment_ready") is not True:
            reasons.append("cv_attachment_not_ready")
        if data.get("subject_exact_vacancy_title") is not True:
            reasons.append("subject_not_exact_vacancy_title")
    return {"pass": not reasons, "stage": stage, "reasons": reasons}
