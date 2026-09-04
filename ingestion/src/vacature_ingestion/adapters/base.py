from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Iterable

from ..hashing import content_hash
from ..models import OBSERVATION_CONTRACT_VERSION, SourceSpec
from ..normalize import clean_text, normalize_canonical_url, weak_fingerprint


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Adapter(ABC):
    name: str

    @abstractmethod
    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def normalize_records(self, records: Iterable[dict[str, Any]], spec: SourceSpec, now: str | None = None) -> list[dict[str, Any]]:
        timestamp = now or utc_now()
        out: list[dict[str, Any]] = []
        for index, record in enumerate(records):
            if index >= spec.max_jobs:
                break
            if not isinstance(record, dict):
                continue
            row = self.normalize_record(record, spec, timestamp)
            if not row:
                continue
            row["canonical_url"] = normalize_canonical_url(row.get("canonical_url") or row.get("url"))
            if not row.get("canonical_url") and not (row.get("source_id") and row.get("source_job_id")):
                continue
            row["observation_contract_version"] = OBSERVATION_CONTRACT_VERSION
            row["ingestion_timestamp"] = timestamp
            row.setdefault("first_seen_at", timestamp)
            row.setdefault("last_seen_at", timestamp)
            row["duplicate_candidate_fingerprint"] = weak_fingerprint(row)
            row["content_hash"] = content_hash(row)
            out.append(row)
        return out


def source_job_id(spec: SourceSpec, provider_job_id: Any) -> str | None:
    value = clean_text(provider_job_id, max_chars=1000)
    return f"{spec.account}:{value}" if value else None
