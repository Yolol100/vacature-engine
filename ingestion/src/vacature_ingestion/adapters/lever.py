from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


class LeverAdapter(Adapter):
    name = "lever"

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        limit = min(100, max(1, int(spec.options.get("page_size", 100))))
        base = spec.endpoint or f"https://api.lever.co/v0/postings/{quote(spec.account)}"
        jobs: list[dict[str, Any]] = []
        skip = 0
        while len(jobs) < spec.max_jobs:
            params = urlencode({"mode": "json", "skip": skip, "limit": limit})
            payload = client.get_json(f"{base}?{params}")
            if not isinstance(payload, list):
                raise ValueError("Lever payload must be a list")
            page = [row for row in payload if isinstance(row, dict)]
            jobs.extend(page)
            if len(page) < limit:
                break
            skip += len(page)
            if skip >= spec.max_jobs:
                break
        return jobs[: spec.max_jobs]

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        title = clean_text(record.get("text"))
        url = clean_text(record.get("hostedUrl"))
        if not title or not url:
            return None
        categories = record.get("categories") if isinstance(record.get("categories"), dict) else {}
        description = record.get("descriptionPlain") or record.get("description")
        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, record.get("id")),
            "source_instance": spec.instance_id,
            "source_url": spec.endpoint or f"lever://{spec.account}",
            "canonical_url": url,
            "url": url,
            "employer": spec.employer or spec.account,
            "title": title,
            "location": clean_text(categories.get("location")),
            "description": html_to_text(description),
            "published_at": None,
            "updated_at": None,
            "valid_through": None,
            "employment_type": clean_text(categories.get("commitment")),
            "salary": record.get("salaryRange") if isinstance(record.get("salaryRange"), dict) else None,
            "listing_language": spec.listing_language,
            "apply_url": clean_text(record.get("applyUrl")) or url,
            "remote": True if clean_text(record.get("workplaceType")) == "remote" else None,
            "workplace_type": clean_text(record.get("workplaceType")),
            "source_metadata": {
                "provider": "lever",
                "provider_job_id": record.get("id"),
                "team": categories.get("team"),
                "department": categories.get("department"),
                "all_locations": categories.get("allLocations"),
                "country": record.get("country"),
                "workplace_type": record.get("workplaceType"),
            },
        }
