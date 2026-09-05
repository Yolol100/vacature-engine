from __future__ import annotations

from typing import Any

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


class RemoteOkAdapter(Adapter):
    name = "remoteok"

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        endpoint = spec.endpoint or "https://remoteok.com/api"
        payload = client.get_json(endpoint)
        if not isinstance(payload, list):
            raise ValueError("Remote OK API payload must be a list")
        jobs: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            # The first API item is metadata/terms, not a vacancy.
            if not item.get("id") or not item.get("position"):
                continue
            jobs.append(item)
            if len(jobs) >= spec.max_jobs:
                break
        return jobs

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        title = clean_text(record.get("position"))
        url = clean_text(record.get("apply_url") or record.get("url"))
        if not title or not url:
            return None
        tags = record.get("tags") if isinstance(record.get("tags"), list) else []
        salary = None
        salary_min = record.get("salary_min")
        salary_max = record.get("salary_max")
        if salary_min not in (None, 0, "0") or salary_max not in (None, 0, "0"):
            salary = {"min": salary_min, "max": salary_max, "currency": None, "period": None}
        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, record.get("id")),
            "source_instance": spec.instance_id,
            "source_url": spec.endpoint or "https://remoteok.com/api",
            "canonical_url": url,
            "url": url,
            "employer": clean_text(record.get("company")),
            "title": title,
            "location": clean_text(record.get("location")) or "Remote",
            "description": html_to_text(record.get("description")),
            "published_at": clean_text(record.get("date")),
            "updated_at": None,
            "valid_through": None,
            "employment_type": None,
            "salary": salary,
            "listing_language": spec.listing_language,
            "apply_url": url,
            "remote": True,
            "workplace_type": "remote",
            "source_metadata": {
                "provider": "remoteok",
                "provider_job_id": record.get("id"),
                "slug": record.get("slug"),
                "tags": tags,
                "epoch": record.get("epoch"),
                "attribution_required": True,
                "canonical_verification_required": True,
            },
        }
