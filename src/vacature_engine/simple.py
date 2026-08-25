from __future__ import annotations

from datetime import date
from typing import Any

MIN_MONTHLY_EUR = 3500.0
MAX_AGE_DAYS = 120
TARGET_YEAR = 2026
MAX_RESULTS = 10
MIN_OUTPUT_SCORE = 75.0
MIN_CORE_FIT = 40.0
MIN_EVIDENCE_FIT = 10.0
CORE_FIT_ANCHORS = {0.0, 25.0, 40.0, 50.0}
EVIDENCE_FIT_ANCHORS = {0.0, 10.0, 18.0, 25.0}
WORKSTYLE_FIT_ANCHORS = {0.0, 5.0, 10.0, 15.0}
LOGIC_VERSION = "2026-08-26-simple-v5"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _posted_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


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


def eligibility(vacancy: dict[str, Any], *, today: date) -> dict[str, Any]:
    reasons: list[str] = []

    posted = _posted_date(vacancy.get("posted_date"))
    age_days: int | None = None
    if posted is None:
        reasons.append("date_missing")
    else:
        age_days = (today - posted).days
        if posted.year != TARGET_YEAR:
            reasons.append("not_2026")
        if age_days < 0:
            reasons.append("future_date")
        elif age_days > MAX_AGE_DAYS:
            reasons.append("older_than_120_days")

    if vacancy.get("fully_remote") is not True:
        reasons.append("not_remote")
    if vacancy.get("geography_compatible") is not True:
        reasons.append("country_restriction")
    if vacancy.get("wordpress_related") is not True:
        reasons.append("not_wordpress_related")
    if vacancy.get("central_hard_mismatch") is True:
        reasons.append("central_hard_mismatch")

    salary = _number(vacancy.get("salary_monthly_eur"))
    salary_known = salary is not None
    if salary_known and salary < MIN_MONTHLY_EUR:
        reasons.append("salary_below_3500")

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


def top_vacancies(vacancies: list[dict[str, Any]], *, today: date) -> list[dict[str, Any]]:
    known_salary: list[dict[str, Any]] = []
    unknown_salary: list[dict[str, Any]] = []

    for item in vacancies:
        gate = eligibility(item, today=today)
        if not gate["pass"]:
            continue
        ranked = dict(item)
        ranked["age_days"] = gate["age_days"]
        ranked["salary_known"] = gate["salary_known"]
        ranked["score"] = score(ranked, age_days=int(gate["age_days"] or 0))
        if ranked["score"] < MIN_OUTPUT_SCORE:
            continue
        if float(ranked["core_fit"]) < MIN_CORE_FIT:
            continue
        if float(ranked["evidence_fit"]) < MIN_EVIDENCE_FIT:
            continue
        (known_salary if gate["salary_known"] else unknown_salary).append(ranked)

    def key(row: dict[str, Any]) -> tuple[float, float, float, int]:
        return (
            float(row["score"]),
            float(row["core_fit"]),
            float(row["evidence_fit"]),
            -(row["age_days"] or 0),
        )

    known_salary.sort(key=key, reverse=True)
    unknown_salary.sort(key=key, reverse=True)
    return (known_salary + unknown_salary)[:MAX_RESULTS]


def choose_language(
    *,
    explicit_language: str | None = None,
    form_language: str | None = None,
    vacancy_language: str | None = None,
) -> str:
    value = explicit_language or form_language or vacancy_language or "English"
    normalized = value.strip().lower()
    aliases = {
        "dutch": "nl",
        "nederlands": "nl",
        "nl": "nl",
        "english": "en",
        "engels": "en",
        "en": "en",
    }
    return aliases.get(normalized, normalized)
