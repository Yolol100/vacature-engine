from __future__ import annotations

from datetime import date
from typing import Any

MIN_MONTHLY_EUR = 3500.0
MAX_AGE_DAYS = 120
TARGET_YEAR = 2026
MAX_RESULTS = 10
UNKNOWN_SALARY_MIN_SCORE = 75.0
LOGIC_VERSION = "2026-08-25-simple-v2"


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


def eligibility(vacancy: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
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
    if core_fit is None or not 0 <= core_fit <= 50:
        raise ValueError("core_fit must be 0..50")
    if evidence_fit is None or not 0 <= evidence_fit <= 25:
        raise ValueError("evidence_fit must be 0..25")
    if workstyle_fit is None or not 0 <= workstyle_fit <= 15:
        raise ValueError("workstyle_fit must be 0..15")
    recency = max(0.0, 10.0 * (1.0 - min(age_days, MAX_AGE_DAYS) / MAX_AGE_DAYS))
    return round(core_fit + evidence_fit + workstyle_fit + recency, 1)


def top_vacancies(vacancies: list[dict[str, Any]], *, today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
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
        if not gate["salary_known"] and ranked["score"] < UNKNOWN_SALARY_MIN_SCORE:
            continue
        (known_salary if gate["salary_known"] else unknown_salary).append(ranked)

    key = lambda row: (row["score"], -(row["age_days"] or 0))
    known_salary.sort(key=key, reverse=True)
    unknown_salary.sort(key=key, reverse=True)
    return (known_salary + unknown_salary)[:MAX_RESULTS]


def choose_language(
    *, explicit_language: str | None = None,
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
