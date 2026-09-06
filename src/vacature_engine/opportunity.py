from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


OPPORTUNITY_CONTRACT_VERSION = "1.0"

RouteType = Literal["employer", "ats", "job_board", "other"]


@dataclass(frozen=True)
class OpportunityAssessment:
    score: int
    freshness_points: int
    route_points: int
    competition_points: int
    deadline_points: int
    verification_points: int
    warnings: tuple[str, ...]


def _freshness_points(age_hours: float | None) -> tuple[int, str | None]:
    if age_hours is None:
        return 8, "freshness_unknown"
    if age_hours < 0:
        raise ValueError("age_hours must be >= 0")
    if age_hours <= 1:
        return 35, None
    if age_hours <= 6:
        return 32, None
    if age_hours <= 24:
        return 27, None
    if age_hours <= 72:
        return 20, None
    if age_hours <= 168:
        return 12, None
    if age_hours <= 720:
        return 6, None
    return 2, None


def _route_points(route_type: RouteType) -> int:
    points = {
        "employer": 25,
        "ats": 23,
        "job_board": 15,
        "other": 8,
    }
    try:
        return points[route_type]
    except KeyError as exc:
        raise ValueError("route_type must be employer, ats, job_board or other") from exc


def _competition_points(applicant_count: int | None) -> tuple[int, str | None]:
    if applicant_count is None:
        return 8, "applicant_count_unknown"
    if isinstance(applicant_count, bool) or applicant_count < 0:
        raise ValueError("applicant_count must be a non-negative integer")
    if applicant_count <= 10:
        return 20, None
    if applicant_count <= 25:
        return 17, None
    if applicant_count <= 50:
        return 13, None
    if applicant_count <= 100:
        return 8, None
    return 4, None


def _deadline_points(deadline_hours: float | None) -> tuple[int, str | None]:
    if deadline_hours is None:
        return 4, "deadline_unknown"
    if deadline_hours < 0:
        raise ValueError("deadline_hours must be >= 0")
    if deadline_hours <= 72:
        return 10, None
    if deadline_hours <= 168:
        return 8, None
    if deadline_hours <= 336:
        return 6, None
    return 4, None


def assess_opportunity(
    *,
    age_hours: float | None,
    route_type: RouteType,
    applicant_count: int | None = None,
    deadline_hours: float | None = None,
    canonical_verified: bool,
) -> OpportunityAssessment:
    """Return an advisory opportunity score based only on explicit operational signals.

    The score is intentionally independent from candidate fit, eligibility, salary and
    ranking. Unknown evidence receives conservative neutral points plus warnings.
    """

    if not isinstance(canonical_verified, bool):
        raise TypeError("canonical_verified must be bool")

    freshness_points, freshness_warning = _freshness_points(age_hours)
    route_points = _route_points(route_type)
    competition_points, competition_warning = _competition_points(applicant_count)
    deadline_points, deadline_warning = _deadline_points(deadline_hours)
    verification_points = 10 if canonical_verified else 0

    warnings = tuple(
        warning
        for warning in (freshness_warning, competition_warning, deadline_warning)
        if warning is not None
    )
    score = (
        freshness_points
        + route_points
        + competition_points
        + deadline_points
        + verification_points
    )

    return OpportunityAssessment(
        score=score,
        freshness_points=freshness_points,
        route_points=route_points,
        competition_points=competition_points,
        deadline_points=deadline_points,
        verification_points=verification_points,
        warnings=warnings,
    )
