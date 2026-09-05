from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


class HimalayasAdapter(Adapter):
    name = "himalayas"

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        base = spec.endpoint or "https://himalayas.app/jobs/api"
        offset = 0
        limit = 20
        jobs: list[dict[str, Any]] = []
        while len(jobs) < spec.max_jobs:
            params = {"offset": offset, "limit": limit}
            sep = "&" if "?" in base else "?"
            payload = client.get_json(f"{base}{sep}{urlencode(params)}")
            batch = payload.get("jobs", []) if isinstance(payload, dict) else []
            if not isinstance(batch, list):
                raise ValueError("Himalayas payload jobs must be a list")
            jobs.extend(item for item in batch if isinstance(item, dict))
            if not batch:
                break
            total_count = payload.get("totalCount") if isinstance(payload, dict) else None
            offset += len(batch)
            if isinstance(total_count, int) and offset >= total_count:
                break
            if len(batch) < limit and total_count is None:
                break
        return jobs[: spec.max_jobs]

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        title = clean_text(record.get("title"))
        url = clean_text(record.get("applicationLink"))
        if not title or not url:
            return None
        restrictions = record.get("locationRestrictions") if isinstance(record.get("locationRestrictions"), list) else []
        location = ", ".join(
            clean_text(item.get("name")) for item in restrictions if isinstance(item, dict) and clean_text(item.get("name"))
        ) or "Worldwide"
        salary = None
        if record.get("minSalary") is not None or record.get("maxSalary") is not None:
            salary = {
                "min": record.get("minSalary"),
                "max": record.get("maxSalary"),
                "currency": clean_text(record.get("currency")),
                "period": clean_text(record.get("salaryPeriod")),
            }
        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, record.get("guid")),
            "source_instance": spec.instance_id,
            "source_url": spec.endpoint or "https://himalayas.app/jobs/api",
            "canonical_url": url,
            "url": url,
            "employer": clean_text(record.get("companyName")),
            "title": title,
            "location": location,
            "description": html_to_text(record.get("description")),
            "published_at": clean_text(record.get("pubDate")),
            "updated_at": None,
            "valid_through": clean_text(record.get("expiryDate")),
            "employment_type": clean_text(record.get("employmentType")),
            "salary": salary,
            "listing_language": spec.listing_language,
            "apply_url": url,
            "remote": True,
            "workplace_type": "remote",
            "source_metadata": {
                "provider": "himalayas",
                "provider_job_id": record.get("guid"),
                "company_slug": record.get("companySlug"),
                "location_restrictions": restrictions,
                "timezone_restrictions": record.get("timezoneRestrictions"),
                "categories": record.get("categories"),
            },
        }
