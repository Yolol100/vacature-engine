from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

from .adapters import AdapterRegistry
from .errors import VacancyEngineError
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
    return max(0.0, (current - posted).total_seconds() / 86400)


def deduplicate(jobs: Iterable[JobRecord]) -> list[JobRecord]:
    seen: set[str] = set()
    result: list[JobRecord] = []
    for job in jobs:
        if job.raw.get("requires_canonical_job_resolution") is True:
            key = f"source:{job.source}:{job.source_job_id}"
        else:
            try:
                key = f"url:{job.canonical_url}"
            except ValueError:
                key = f"source:{job.source}:{job.source_job_id}"
        if key in seen:
            continue
        seen.add(key)
        result.append(job)
    return result


def filter_recency(jobs: Iterable[JobRecord], days_back: float) -> tuple[list[JobRecord], list[JobRecord]]:
    if days_back < 0:
        raise ValueError("days_back must be >= 0")
    fresh: list[JobRecord] = []
    unknown: list[JobRecord] = []
    for job in jobs:
        age = posted_age_days(job)
        if age is None:
            unknown.append(job)
        elif age <= days_back:
            fresh.append(job)
    return fresh, unknown


def fetch_source(spec: SourceSpec) -> list[JobRecord]:
    options = spec.options or {}
    return AdapterRegistry.create(spec.source, spec.slug, **options).fetch()


def fetch_many(specs: Iterable[SourceSpec], *, max_workers: int = 4) -> BatchResult:
    specs = list(specs)
    if max_workers < 1 or max_workers > 8:
        raise ValueError("max_workers must be between 1 and 8")
    jobs: list[JobRecord] = []
    failures: list[SourceFailure] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(fetch_source, spec): spec for spec in specs}
        for future in as_completed(future_map):
            spec = future_map[future]
            try:
                jobs.extend(future.result())
            except VacancyEngineError as exc:
                failures.append(SourceFailure(spec.source, spec.slug, exc.category.value, str(exc), exc.retryable))
            except (ValueError, RuntimeError, OSError) as exc:
                failures.append(SourceFailure(spec.source, spec.slug, "parsing/structure change", str(exc), False))
    return BatchResult(deduplicate(jobs), failures)
