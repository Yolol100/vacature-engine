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


@dataclass
class SourceRunResult:
    source_instance: str
    success: bool
    fetched: int
    normalized: int
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

    def _review_queue(self, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        queue: list[dict[str, Any]] = []
        for row in observations:
            change = self.state.observation_change_state(row)
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
            observations = adapter.normalize_records(records, spec, now=started_at)
            review_observations = self._review_queue(observations)
            counts = self.state.upsert_observations(
                observations,
                source_instance=spec.instance_id,
                run_id=run_id,
                missing_close_threshold=spec.missing_close_threshold,
                complete_snapshot=True,
            )
            self.state.finish_run(run_id, success=True, fetched=len(records), normalized=len(observations), counts=counts)
            return SourceRunResult(
                source_instance=spec.instance_id, success=True, fetched=len(records), normalized=len(observations),
                new=counts.new, updated=counts.updated, unchanged=counts.unchanged,
                duplicate_observations=counts.duplicate_observations, missing=counts.missing, closed=counts.closed,
                duration_seconds=time.perf_counter() - t0, observations=observations,
                review_observations=review_observations,
            )
        except Exception as exc:
            category = exc.category if isinstance(exc, FetchError) else "parsing_or_adapter_failure"
            self.state.finish_run(run_id, success=False, fetched=0, normalized=0,
                                  failure_category=category, failure_message=str(exc))
            return SourceRunResult(
                source_instance=spec.instance_id, success=False, fetched=0, normalized=0,
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
        run_id = self.state.start_run(spec.instance_id, started_at)
        t0 = time.perf_counter()
        observations = adapter.normalize_records(records, spec, now=started_at)
        review_observations = self._review_queue(observations)
        counts = self.state.upsert_observations(
            observations, source_instance=spec.instance_id, run_id=run_id,
            missing_close_threshold=spec.missing_close_threshold, complete_snapshot=complete_snapshot,
        )
        self.state.finish_run(run_id, success=True, fetched=len(records), normalized=len(observations), counts=counts)
        return SourceRunResult(
            source_instance=spec.instance_id, success=True, fetched=len(records), normalized=len(observations),
            new=counts.new, updated=counts.updated, unchanged=counts.unchanged,
            duplicate_observations=counts.duplicate_observations, missing=counts.missing, closed=counts.closed,
            duration_seconds=time.perf_counter() - t0, observations=observations,
            review_observations=review_observations,
        )
