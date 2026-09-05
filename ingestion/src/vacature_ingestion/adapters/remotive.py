from __future__ import annotations

from typing import Any

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


class RemotiveAdapter(Adapter):
    name = "remotive"

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        endpoint = spec.endpoint or "https://remotive.com/api/remote-jobs"
        payload = client.get_json(endpoint)
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        if not isinstance(jobs, list):
            raise ValueError("Remotive payload jobs must be a list")
        return [item for item in jobs if isinstance(item, dict)][: spec.max_jobs]

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        title = clean_text(record.get("title"))
        url = clean_text(record.get("url"))
        if not title or not url:
            return None
        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, record.get("id")),
            "source_instance": spec.instance_id,
            "source_url": spec.endpoint or "https://remotive.com/api/remote-jobs",
            "canonical_url": url,
            "url": url,
            "employer": clean_text(record.get("company_name")),
            "title": title,
            "location": clean_text(record.get("candidate_required_location")) or "Remote",
            "description": html_to_text(record.get("description")),
            "published_at": clean_text(record.get("publication_date")),
            "updated_at": None,
            "valid_through": None,
            "employment_type": clean_text(record.get("job_type")),
            "salary": clean_text(record.get("salary")),
            "listing_language": spec.listing_language,
            "apply_url": url,
            "remote": True,
            "workplace_type": "remote",
            "source_metadata": {
                "provider": "remotive",
                "provider_job_id": record.get("id"),
                "category": record.get("category"),
                "tags": record.get("tags"),
                "attribution_required": True,
                "delayed_feed": True,
            },
        }
