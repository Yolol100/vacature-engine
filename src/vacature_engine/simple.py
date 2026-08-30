from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
import math
from typing import Any

CORE_FIT_ANCHORS = {0.0, 25.0, 40.0, 50.0}
EVIDENCE_FIT_ANCHORS = {0.0, 10.0, 18.0, 25.0}
WORKSTYLE_FIT_ANCHORS = {0.0, 5.0, 10.0, 15.0}
LOGIC_VERSION = "2026-08-30-language-gate-v10"

_LANGUAGE_ALIASES = {
    "dutch": "nl",
    "nederlands": "nl",
    "nl": "nl",
    "english": "en",
    "engels": "en",
    "en": "en",
}


@dataclass(frozen=True, slots=True)
class VacancyPolicy:
    min_monthly_salary_eur: float
    max_posting_age_days: int
    max_output_roles: int
    min_output_score: float
    min_core_fit: float
    min_evidence_fit: float
    allowed_listing_languages: frozenset[str] | None = None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def _policy_number(config: Mapping[str, Any], key: str, *, integer: bool = False) -> float | int:
    if key not in config:
        raise ValueError(f"policy missing required Config key: {key}")
    value = config[key]
    if isinstance(value, bool) or value is None:
        raise ValueError(f"policy key {key} must be numeric")
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError as exc:
            raise ValueError(f"policy key {key} must be numeric") from exc
    elif isinstance(value, (int, float)):
        number = float(value)
    else:
        raise ValueError(f"policy key {key} must be numeric")
    if not math.isfinite(number):
        raise ValueError(f"policy key {key} must be finite")
    if integer:
        if not number.is_integer():
            raise ValueError(f"policy key {key} must be an integer")
        return int(number)
    return number


def _normalize_language(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace("_", "-")
    if not normalized:
        return None
    normalized = _LANGUAGE_ALIASES.get(normalized, normalized)
    if normalized.startswith("nl-"):
        return "nl"
    if normalized.startswith("en-"):
        return "en"
    return normalized


def _policy_languages(config: Mapping[str, Any], key: str) -> frozenset[str]:
    value = config[key]
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, (list, tuple, set, frozenset)):
        raw_items = list(value)
    else:
        raise ValueError(f"policy key {key} must be CSV text or a language list")

    languages: set[str] = set()
    for item in raw_items:
        normalized = _normalize_language(item)
        if normalized is None or len(normalized) != 2 or not normalized.isalpha():
            raise ValueError(f"policy key {key} contains an invalid language")
        languages.add(normalized)
    if not languages:
        raise ValueError(f"policy key {key} must contain at least one language")
    return frozenset(languages)


def policy_from_config(config: Mapping[str, Any]) -> VacancyPolicy:
    policy = VacancyPolicy(
        min_monthly_salary_eur=float(_policy_number(config, "min_monthly_salary_eur")),
        max_posting_age_days=int(_policy_number(config, "max_posting_age_days", integer=True)),
        max_output_roles=int(_policy_number(config, "max_output_roles", integer=True)),
        min_output_score=float(_policy_number(config, "min_output_score")),
        min_core_fit=float(_policy_number(config, "min_core_fit")),
        min_evidence_fit=float(_policy_number(config, "min_evidence_fit")),
        allowed_listing_languages=(
            _policy_languages(config, "allowed_listing_languages")
            if "allowed_listing_languages" in config
            else None
        ),
    )
    if policy.min_monthly_salary_eur < 0:
        raise ValueError("min_monthly_salary_eur must be >= 0")
    if policy.max_posting_age_days < 0:
        raise ValueError("max_posting_age_days must be >= 0")
    if policy.max_output_roles < 1:
        raise ValueError("max_output_roles must be >= 1")
    if not 0 <= policy.min_output_score <= 100:
        raise ValueError("min_output_score must be between 0 and 100")
    if not 0 <= policy.min_core_fit <= 50:
        raise ValueError("min_core_fit must be between 0 and 50")
    if not 0 <= policy.min_evidence_fit <= 25:
        raise ValueError("min_evidence_fit must be between 0 and 25")
    return policy


def _coerce_policy(policy: VacancyPolicy | Mapping[str, Any]) -> VacancyPolicy:
    if isinstance(policy, VacancyPolicy):
        return policy
    if isinstance(policy, Mapping):
        return policy_from_config(policy)
    raise TypeError("policy must be VacancyPolicy or a Config mapping")


def _posted_date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    if len(value) > 10 and value[10] not in {"T", " "}:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _salary_status(vacancy: Mapping[str, Any], minimum: float) -> tuple[bool, str | None]:
    exact_raw = vacancy.get("salary_monthly_eur")
    minimum_raw = vacancy.get("salary_min_monthly_eur")
    maximum_raw = vacancy.get("salary_max_monthly_eur")
    exact_present = exact_raw is not None
    range_present = minimum_raw is not None or maximum_raw is not None

    if exact_present and range_present:
        return False, "salary_invalid"

    if exact_present:
        exact = _number(exact_raw)
        if exact is None or exact < 0:
            return False, "salary_invalid"
        if exact < minimum:
            return True, "salary_below_minimum"
        return True, None

    if range_present:
        low = _number(minimum_raw) if minimum_raw is not None else None
        high = _number(maximum_raw) if maximum_raw is not None else None
        if minimum_raw is not None and (low is None or low < 0):
            return False, "salary_invalid"
        if maximum_raw is not None and (high is None or high < 0):
            return False, "salary_invalid"
        if low is not None and high is not None and low > high:
            return False, "salary_invalid"
        if high is not None and high < minimum:
            return True, "salary_below_minimum"
        return True, None

    return False, None


def _required_languages(value: Any) -> tuple[bool, set[str]]:
    if value is None:
        return True, set()
    if isinstance(value, str):
        raw_items = [part for part in value.split(",") if part.strip()]
    elif isinstance(value, (list, tuple, set, frozenset)):
        raw_items = list(value)
    else:
        return False, set()

    languages: set[str] = set()
    for item in raw_items:
        normalized = _normalize_language(item)
        if normalized is None:
            return False, set()
        languages.add(normalized)
    return True, languages


def _recency_points(age_days: int) -> float:
    if age_days <= 14:
        return 10.0
    if age_days <= 30:
        return 8.0
    if age_days <= 60:
        return 6.0
    if age_days <= 90:
        return 4.0
    return 2.0


def eligibility(
    vacancy: dict[str, Any],
    *,
    today: date,
    policy: VacancyPolicy | Mapping[str, Any],
) -> dict[str, Any]:
    runtime_policy = _coerce_policy(policy)
    reasons: list[str] = []

    posted = _posted_date(vacancy.get("posted_date"))
    age_days: int | None = None
    if posted is None:
        reasons.append("date_missing")
    else:
        age_days = (today - posted).days
        if age_days < 0:
            reasons.append("future_date")
        elif age_days > runtime_policy.max_posting_age_days:
            reasons.append("older_than_max_age")

    if vacancy.get("fully_remote") is not True:
        reasons.append("not_remote")
    if vacancy.get("geography_compatible") is not True:
        reasons.append("country_restriction")
    if vacancy.get("wordpress_related") is not True:
        reasons.append("not_wordpress_related")
    if vacancy.get("central_hard_mismatch") is True:
        reasons.append("central_hard_mismatch")

    if runtime_policy.allowed_listing_languages is not None:
        listing_language = _normalize_language(vacancy.get("listing_language"))
        if listing_language is None:
            reasons.append("listing_language_missing")
        elif listing_language not in runtime_policy.allowed_listing_languages:
            reasons.append("listing_language_not_allowed")

        application_language = _normalize_language(vacancy.get("application_language"))
        if application_language is None:
            reasons.append("application_language_missing")
        elif application_language not in runtime_policy.allowed_listing_languages:
            reasons.append("application_language_not_allowed")

        required_languages_valid, required_languages = _required_languages(vacancy.get("required_languages"))
        if not required_languages_valid:
            reasons.append("required_languages_invalid")
        elif required_languages - runtime_policy.allowed_listing_languages:
            reasons.append("required_language_not_allowed")

    salary_known, salary_reason = _salary_status(vacancy, runtime_policy.min_monthly_salary_eur)
    if salary_reason is not None:
        reasons.append(salary_reason)

    return {
        "pass": not reasons,
        "reasons": reasons,
        "age_days": age_days,
        "salary_known": salary_known,
        "logic_version": LOGIC_VERSION,
    }


def score(vacancy: dict[str, Any], *, age_days: int) -> float:
    core_fit = _number(vacancy.get("core_fit"))
    evidence_fit = _number(vacancy.get("evidence_fit"))
    workstyle_fit = _number(vacancy.get("workstyle_fit"))
    if core_fit not in CORE_FIT_ANCHORS:
        raise ValueError("core_fit must use 0, 25, 40, or 50")
    if evidence_fit not in EVIDENCE_FIT_ANCHORS:
        raise ValueError("evidence_fit must use 0, 10, 18, or 25")
    if workstyle_fit not in WORKSTYLE_FIT_ANCHORS:
        raise ValueError("workstyle_fit must use 0, 5, 10, or 15")
    return core_fit + evidence_fit + workstyle_fit + _recency_points(age_days)


def top_vacancies(
    vacancies: list[Any],
    *,
    today: date,
    policy: VacancyPolicy | Mapping[str, Any],
) -> list[dict[str, Any]]:
    runtime_policy = _coerce_policy(policy)
    known_salary: list[dict[str, Any]] = []
    unknown_salary: list[dict[str, Any]] = []

    for item in vacancies:
        if not isinstance(item, dict):
            continue
        gate = eligibility(item, today=today, policy=runtime_policy)
        if not gate["pass"]:
            continue
        ranked = dict(item)
        ranked["age_days"] = gate["age_days"]
        ranked["salary_known"] = gate["salary_known"]
        try:
            ranked["score"] = score(ranked, age_days=int(gate["age_days"] or 0))
            core_fit = float(ranked["core_fit"])
            evidence_fit = float(ranked["evidence_fit"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if ranked["score"] < runtime_policy.min_output_score:
            continue
        if core_fit < runtime_policy.min_core_fit:
            continue
        if evidence_fit < runtime_policy.min_evidence_fit:
            continue
        (known_salary if gate["salary_known"] else unknown_salary).append(ranked)

    def key(row: dict[str, Any]) -> tuple[float, float, float, int, str, str]:
        return (
            float(row["score"]),
            float(row["core_fit"]),
            float(row["evidence_fit"]),
            -(row["age_days"] or 0),
            str(row.get("canonical_url") or row.get("url") or ""),
            str(row.get("title") or ""),
        )

    known_salary.sort(key=key, reverse=True)
    unknown_salary.sort(key=key, reverse=True)
    return (known_salary + unknown_salary)[: runtime_policy.max_output_roles]


def choose_language(
    *,
    explicit_language: str | None = None,
    form_language: str | None = None,
    vacancy_language: str | None = None,
) -> str:
    value = explicit_language or form_language or vacancy_language or "English"
    return _normalize_language(value) or "en"
