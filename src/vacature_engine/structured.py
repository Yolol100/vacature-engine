from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

STRUCTURED_JOBPOSTING_CONTRACT_VERSION = "1.0"


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.strip().split())
    return text or None


def _iso_date(value: Any) -> tuple[str | None, bool | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, False
    raw = value.strip()
    if len(raw) < 10 or (len(raw) > 10 and raw[10] not in {"T", " ", "Z", "+", "-"}):
        return None, False
    try:
        parsed = date.fromisoformat(raw[:10])
    except ValueError:
        return None, False
    return parsed.isoformat(), True


def _type_values(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.casefold()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return {item.casefold() for item in value if isinstance(item, str)}
    return set()


def _names(value: Any) -> list[str]:
    items = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else [value]
    names: set[str] = set()
    for item in items:
        if isinstance(item, str):
            text = _clean_text(item)
            if text:
                names.add(text)
        elif isinstance(item, Mapping):
            text = _clean_text(item.get("name"))
            if text:
                names.add(text)
    return sorted(names)


def _identifier_value(value: Any) -> str | None:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, Mapping):
        return _clean_text(value.get("value")) or _clean_text(value.get("name"))
    return None


def _organization_name(value: Any) -> str | None:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, Mapping):
        return _clean_text(value.get("name"))
    return None


def _employment_types(value: Any) -> list[str]:
    if isinstance(value, str):
        text = _clean_text(value)
        return [text] if text else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return sorted({text for item in value if (text := _clean_text(item))})
    return []


def _salary_signals(value: Any) -> dict[str, Any]:
    result = {
        "base_salary_present": value is not None,
        "base_salary_currency": None,
        "base_salary_unit": None,
        "base_salary_value": None,
        "base_salary_min_value": None,
        "base_salary_max_value": None,
    }
    if not isinstance(value, Mapping):
        return result
    result["base_salary_currency"] = _clean_text(value.get("currency"))
    salary_value = value.get("value")
    if isinstance(salary_value, Mapping):
        result["base_salary_unit"] = _clean_text(salary_value.get("unitText"))
        for source_key, target_key in (
            ("value", "base_salary_value"),
            ("minValue", "base_salary_min_value"),
            ("maxValue", "base_salary_max_value"),
        ):
            number = salary_value.get(source_key)
            if isinstance(number, (int, float)) and not isinstance(number, bool):
                result[target_key] = number
    return result


def jobposting_signals(jobposting: Mapping[str, Any], *, today: date) -> dict[str, Any]:
    """Extract conservative Schema.org JobPosting evidence without policy inference.

    The result is supplemental evidence only. It does not decide open status,
    fully-remote eligibility, geography compatibility, salary normalization, or fit.
    """
    types = _type_values(jobposting.get("@type"))
    date_posted, date_posted_valid = _iso_date(jobposting.get("datePosted"))
    valid_through, valid_through_valid = _iso_date(jobposting.get("validThrough"))

    posted_future = None
    if date_posted_valid and date_posted:
        posted_future = date.fromisoformat(date_posted) > today

    expired_by_valid_through = None
    if valid_through_valid and valid_through:
        expired_by_valid_through = date.fromisoformat(valid_through) < today

    location_types = _type_values(jobposting.get("jobLocationType"))
    remote_signal = "telecommute" in location_types

    result: dict[str, Any] = {
        "structured_contract_version": STRUCTURED_JOBPOSTING_CONTRACT_VERSION,
        "is_job_posting": "jobposting" in types,
        "identifier": _identifier_value(jobposting.get("identifier")),
        "title": _clean_text(jobposting.get("title")),
        "hiring_organization": _organization_name(jobposting.get("hiringOrganization")),
        "date_posted": date_posted,
        "date_posted_valid": date_posted_valid,
        "date_posted_future": posted_future,
        "valid_through": valid_through,
        "valid_through_valid": valid_through_valid,
        "expired_by_valid_through": expired_by_valid_through,
        "remote_signal": remote_signal,
        "applicant_locations": _names(jobposting.get("applicantLocationRequirements")),
        "job_locations": _names(jobposting.get("jobLocation")),
        "employment_types": _employment_types(jobposting.get("employmentType")),
        "direct_apply": jobposting.get("directApply") if isinstance(jobposting.get("directApply"), bool) else None,
    }
    result.update(_salary_signals(jobposting.get("baseSalary")))
    return result
