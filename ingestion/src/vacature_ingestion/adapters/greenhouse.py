from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


class GreenhouseAdapter(Adapter):
    name = "greenhouse"

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        endpoint = spec.endpoint or f"https://boards-api.greenhouse.io/v1/boards/{quote(spec.account)}/jobs?content=true"
        payload = client.get_json(endpoint)
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        if not isinstance(jobs, list):
            raise ValueError("Greenhouse payload jobs must be a list")
        return jobs[: spec.max_jobs]

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        title = clean_text(record.get("title"))
        url = clean_text(record.get("absolute_url"))
        if not title or not url:
            return None
        location = record.get("location") if isinstance(record.get("location"), dict) else {}
        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, record.get("id")),
            "source_instance": spec.instance_id,
            "source_url": spec.endpoint or f"greenhouse://{spec.account}",
            "canonical_url": url,
            "url": url,
            "employer": spec.employer or spec.account,
            "title": title,
            "location": clean_text(location.get("name")),
            "description": html_to_text(record.get("content")),
            "published_at": None,
            "updated_at": clean_text(record.get("updated_at")),
            "valid_through": None,
            "employment_type": None,
            "salary": None,
            "listing_language": spec.listing_language,
            "apply_url": url,
            "remote": None,
            "workplace_type": None,
            "source_metadata": {
                "provider": "greenhouse",
                "provider_job_id": record.get("id"),
                "internal_job_id": record.get("internal_job_id"),
                "departments": record.get("departments"),
                "offices": record.get("offices"),
            },
        }
