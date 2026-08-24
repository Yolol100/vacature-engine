from __future__ import annotations

import math
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from .adapters import AdapterRegistry
from .core import content_hash, norm
from .errors import FailureCategory, VacancyEngineError
from .models import JobRecord


@dataclass(slots=True)
class SourceSpec:
    source: str
    slug: str
    options: dict[str, Any] | None = None


@dataclass(slots=True)
class SourceFailure:
    source: str
    slug: str
    category: str
    message: str
    retryable: bool


@dataclass(slots=True)
class BatchResult:
    jobs: list[JobRecord]
    failures: list[SourceFailure]

    def to_dict(self) -> dict[str, Any]:
        return {
            "jobs": [job.to_dict() for job in self.jobs],
            "failures": [asdict(failure) for failure in self.failures],
        }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def posted_age_days(job: JobRecord, *, now: datetime | None = None) -> float | None:
    posted = _parse_iso(job.posted_at)
    if posted is None:
        return None
    current = (now or datetime.now(UTC)).astimezone(UTC)
    return (current - posted).total_seconds() / 86400


def _semantic_duplicate_key(job: JobRecord) -> str | None:
    if job.raw.get("requires_canonical_job_resolution") is True:
        return None
    if not job.description or not job.location:
        return None
    try:
        return "semantic:" + "|".join(
            (
                norm(job.employer),
                norm(job.title),
                norm(job.location),
                content_hash(job.description),
            )
        )
    except ValueError:
        return None


def deduplicate(jobs: Iterable[JobRecord]) -> list[JobRecord]:
    seen: set[str] = set()
    result: list[JobRecord] = []
    for job in jobs:
        keys = [f"source:{job.source}:{job.source_job_id}"]
        if job.raw.get("requires_canonical_job_resolution") is not True:
            with suppress(ValueError):
                keys.append(f"url:{job.canonical_url}")
            semantic = _semantic_duplicate_key(job)
            if semantic:
                keys.append(semantic)
        if any(key in seen for key in keys):
            continue
        seen.update(keys)
        result.append(job)
    return result


def filter_recency(jobs: Iterable[JobRecord], days_back: float) -> tuple[list[JobRecord], list[JobRecord]]:
    if (
        isinstance(days_back, bool)
        or not isinstance(days_back, (int, float))
        or not math.isfinite(float(days_back))
        or days_back < 0
    ):
        raise ValueError("days_back must be a finite non-negative number")
    fresh: list[JobRecord] = []
    unknown: list[JobRecord] = []
    for job in jobs:
        age = posted_age_days(job)
        if age is None:
            unknown.append(job)
        elif 0 <= age <= days_back:
            fresh.append(job)
    return fresh, unknown


def fetch_source(spec: SourceSpec) -> list[JobRecord]:
    options = spec.options or {}
    return AdapterRegistry.create(spec.source, spec.slug, **options).fetch()


def fetch_many(specs: Iterable[SourceSpec], *, max_workers: int = 4) -> BatchResult:
    specs = list(specs)
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1 or max_workers > 8:
        raise ValueError("max_workers must be an integer between 1 and 8")
    results: dict[int, list[JobRecord]] = {}
    failure_map: dict[int, SourceFailure] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(fetch_source, spec): (index, spec) for index, spec in enumerate(specs)}
        for future in as_completed(future_map):
            index, spec = future_map[future]
            try:
                results[index] = future.result()
            except VacancyEngineError as exc:
                failure_map[index] = SourceFailure(spec.source, spec.slug, exc.category.value, str(exc), exc.retryable)
            except (ValueError, RuntimeError, OSError) as exc:
                failure_map[index] = SourceFailure(spec.source, spec.slug, FailureCategory.PARSING_CHANGE.value, str(exc), False)
            except Exception as exc:  # isolate one broken source without hiding BaseException
                failure_map[index] = SourceFailure(
                    spec.source, spec.slug, FailureCategory.OTHER.value,
                    f"unexpected adapter error: {type(exc).__name__}: {exc}", False,
                )
    jobs = [job for index in range(len(specs)) for job in results.get(index, [])]
    failures = [failure_map[index] for index in range(len(specs)) if index in failure_map]
    return BatchResult(deduplicate(jobs), failures)
