from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .adapters import ADAPTERS
from .http import FetchError, HttpClient
from .models import SourceSpec
from .state import StateStore


def _registry_source_ids(spec: SourceSpec) -> list[str]:
    source_ids = {str(spec.source_id or "").strip()}
    extra = spec.options.get("registry_source_id") if isinstance(spec.options, dict) else None
    if isinstance(extra, str) and extra.strip():
        source_ids.add(extra.strip())
    elif isinstance(extra, list):
        source_ids.update(str(value).strip() for value in extra if str(value).strip())
    return sorted(value for value in source_ids if value)


@dataclass
class SourceRunResult:
    source_instance: str
    success: bool
    fetched: int
    normalized: int
    registry_source_ids: list[str] | None = None
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicate_observations: int = 0
    missing: int = 0
    closed: int = 0
    failure_category: str | None = None
    failure_message: str | None = None
    duration_seconds: float = 0.0
    observations: list[dict[str, Any]] | None = None
    review_observations: list[dict[str, Any]] | None = None
    quarantine_count: int = 0
    complete_snapshot: bool = False

    def summary(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("observations", None)
        data.pop("review_observations", None)
        return data


class IngestionRunner:
    def __init__(self, state_path: str | Path):
        self.state = StateStore(state_path)

    def close(self) -> None:
        self.state.close()

    def _review_queue(self, observations: list[dict[str, Any]], *, closure_authority: bool = True) -> list[dict[str, Any]]:
        queue: list[dict[str, Any]] = []
        for row in observations:
            change = self.state.observation_change_state(row, closure_authority=closure_authority)
            if change in {"new", "updated"}:
                item = dict(row)
                item["ingestion_change"] = change
                queue.append(item)
        return queue

    def run_source(self, spec: SourceSpec, *, client: HttpClient | None = None) -> SourceRunResult:
        adapter = ADAPTERS.get(spec.adapter)
        if adapter is None:
            raise ValueError(f"unknown adapter: {spec.adapter}")
        client = client or HttpClient(
            timeout_seconds=spec.timeout_seconds,
            retries=spec.retries,
            max_response_bytes=spec.max_response_bytes,
        )
        started_at = datetime.now(timezone.utc).isoformat()
        run_id = self.state.start_run(spec.instance_id, started_at)
        t0 = time.perf_counter()
        try:
            records = adapter.fetch(client, spec)
            batch = adapter.normalize_batch(records, spec, now=started_at)
            observations = batch.observations
            complete_snapshot = not batch.quarantine_count and adapter.is_complete_snapshot(spec, records)
            review_observations = self._review_queue(observations, closure_authority=adapter.complete_snapshot)
            counts = self.state.upsert_observations(
                observations,
                source_instance=spec.instance_id,
                run_id=run_id,
                missing_close_threshold=spec.missing_close_threshold,
                # Search rankings / paginated discoveries are never full source snapshots.
                # Absence from page N must not close an employer's vacancy.
                complete_snapshot=complete_snapshot,
                closure_authority=adapter.complete_snapshot,
            )
            self.state.finish_run(run_id, success=True, fetched=len(records), normalized=len(observations), counts=counts)
            return SourceRunResult(
                source_instance=spec.instance_id, success=True, fetched=len(records), normalized=len(observations),
                registry_source_ids=_registry_source_ids(spec),
                new=counts.new, updated=counts.updated, unchanged=counts.unchanged,
                duplicate_observations=counts.duplicate_observations, missing=counts.missing, closed=counts.closed,
                duration_seconds=time.perf_counter() - t0, observations=observations,
                review_observations=review_observations,
                quarantine_count=batch.quarantine_count, complete_snapshot=complete_snapshot,
            )
        except Exception as exc:
            category = exc.category if isinstance(exc, FetchError) else "parsing_or_adapter_failure"
            self.state.finish_run(run_id, success=False, fetched=0, normalized=0,
                                  failure_category=category, failure_message=str(exc))
            return SourceRunResult(
                source_instance=spec.instance_id, success=False, fetched=0, normalized=0,
                registry_source_ids=_registry_source_ids(spec),
                failure_category=category, failure_message=str(exc), duration_seconds=time.perf_counter() - t0,
                observations=[], review_observations=[],
            )

    def run_many(self, specs: Iterable[SourceSpec]) -> list[SourceRunResult]:
        results: list[SourceRunResult] = []
        for spec in specs:
            results.append(self.run_source(spec))
        return results

    def ingest_records(self, spec: SourceSpec, records: list[dict[str, Any]], *, complete_snapshot: bool = True,
                       now: str | None = None) -> SourceRunResult:
        adapter = ADAPTERS.get(spec.adapter)
        if adapter is None:
            raise ValueError(f"unknown adapter: {spec.adapter}")
        started_at = now or datetime.now(timezone.utc).isoformat()
        t0 = time.perf_counter()
        # Validate the Google source even for empty input. Per-record validation
        # would otherwise be skipped and could erase ATS source memberships.
        if spec.adapter == "serpapi_google":
            adapter._validate_spec(spec)
        # Invalid source specs must leave no unfinished or successful run.
        batch = adapter.normalize_batch(records, spec, now=started_at)
        observations = batch.observations
        complete_snapshot = (complete_snapshot and not batch.quarantine_count
                             and adapter.is_complete_snapshot(spec, records))
        run_id = self.state.start_run(spec.instance_id, started_at)
        review_observations = self._review_queue(observations, closure_authority=adapter.complete_snapshot)
        counts = self.state.upsert_observations(
            observations, source_instance=spec.instance_id, run_id=run_id,
            missing_close_threshold=spec.missing_close_threshold,
            complete_snapshot=complete_snapshot,
            closure_authority=adapter.complete_snapshot,
        )
        self.state.finish_run(run_id, success=True, fetched=len(records), normalized=len(observations), counts=counts)
        return SourceRunResult(
            source_instance=spec.instance_id, success=True, fetched=len(records), normalized=len(observations),
            registry_source_ids=_registry_source_ids(spec),
            new=counts.new, updated=counts.updated, unchanged=counts.unchanged,
            duplicate_observations=counts.duplicate_observations, missing=counts.missing, closed=counts.closed,
            duration_seconds=time.perf_counter() - t0, observations=observations,
            review_observations=review_observations,
            quarantine_count=batch.quarantine_count, complete_snapshot=complete_snapshot,
        )
