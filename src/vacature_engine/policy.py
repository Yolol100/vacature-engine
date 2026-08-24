from __future__ import annotations
from typing import Any

LOGIC_VERSION = "2026-08-24-v2"

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


def hard_gate(data: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    age = data.get("posted_age_days")
    if age is None or not isinstance(age, (int, float)) or age < 0 or age > 7:
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
        if data.get(key) is True:
            reasons.append(reason)

    level = str(data.get("level", "")).strip().lower()
    allowed = ("medior", "mid", "senior", "specialist", "autonomous", "lead", "principal", "consultant", "engineer")
    if not level or not any(term in level for term in allowed):
        reasons.append("level_not_confirmed_medior_or_above")

    mismatch_count = data.get("central_hard_mismatch_count", 0)
    if not isinstance(mismatch_count, int) or mismatch_count < 0:
        reasons.append("invalid_central_hard_mismatch_count")
    elif mismatch_count > 0:
        reasons.append("central_hard_requirement_mismatch")
    return {"pass": not reasons, "reasons": reasons}


def _bounded(data: dict[str, Any], key: str, maximum: float) -> float:
    value = data.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    value = float(value)
    if value < 0 or value > maximum:
        raise ValueError(f"{key} must be between 0 and {maximum}")
    return value


def score(data: dict[str, Any]) -> dict[str, Any]:
    match_parts = {key: _bounded(data, key, maximum) for key, maximum in MATCH_COMPONENTS.items()}
    raw_match = sum(match_parts.values())
    multiple = bool(data.get("multiple_central_hard_mismatches", False))
    central_missing = bool(data.get("central_hard_missing", False))
    match_score = min(raw_match, 59.0) if central_missing else raw_match
    opportunity_parts = {key: _bounded(data, key, maximum) for key, maximum in OPPORTUNITY_COMPONENTS.items()}
    match_contribution = match_score * 0.55
    return {
        "logic_version": LOGIC_VERSION,
        "excluded": multiple,
        "exclusion_reason": "multiple_central_hard_mismatches" if multiple else None,
        "match_components": match_parts,
        "raw_match_score": round(raw_match, 1),
        "match_score": round(match_score, 1),
        "opportunity_components": {"match_contribution": round(match_contribution, 1), **opportunity_parts},
        "opportunity_score": round(match_contribution + sum(opportunity_parts.values()), 1),
    }


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
    if stage == "draft":
        email = str(data.get("recipient_email", "")).strip()
        source = str(data.get("recipient_source_url", "")).strip()
        if data.get("recipient_verified") is not True or not email or "@" not in email or not source.startswith(("http://", "https://")):
            reasons.append("verified_role_application_recipient_missing")
        if data.get("factual_qa") != "pass":
            reasons.append("factual_qa_not_passed")
        if data.get("style_qa") != "pass":
            reasons.append("style_qa_not_passed")
        if data.get("cv_selected") is not True:
            reasons.append("cv_not_selected")
    return {"pass": not reasons, "stage": stage, "reasons": reasons}
