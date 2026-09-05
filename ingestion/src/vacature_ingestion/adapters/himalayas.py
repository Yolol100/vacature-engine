from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


def _restriction_name(value: Any) -> str | None:
    if isinstance(value, dict):
        return clean_text(value.get("name") or value.get("label") or value.get("value"))
    return clean_text(value)


class HimalayasAdapter(Adapter):
    name = "himalayas"

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        query = clean_text(spec.options.get("query")) if isinstance(spec.options, dict) else None
        sort = clean_text(spec.options.get("sort")) if isinstance(spec.options, dict) else None
        jobs: list[dict[str, Any]] = []

        if query:
            base = spec.endpoint or "https://himalayas.app/jobs/api/search"
            page = 1
            seen_ids: set[str] = set()
            while len(jobs) < spec.max_jobs:
                params = {"q": query, "sort": sort or "recent", "page": page}
                sep = "&" if "?" in base else "?"
                payload = client.get_json(f"{base}{sep}{urlencode(params)}")
                batch = payload.get("jobs", []) if isinstance(payload, dict) else []
                if not isinstance(batch, list):
                    raise ValueError("Himalayas search payload jobs must be a list")
                fresh: list[dict[str, Any]] = []
                for item in batch:
                    if not isinstance(item, dict):
                        continue
                    identity = clean_text(item.get("guid")) or clean_text(item.get("applicationLink"))
                    if identity and identity in seen_ids:
                        continue
                    if identity:
                        seen_ids.add(identity)
                    fresh.append(item)
                jobs.extend(fresh)
                if not batch or not fresh:
                    break
                page += 1
                if len(jobs) < spec.max_jobs:
                    time.sleep(0.5)
            return jobs[: spec.max_jobs]

        base = spec.endpoint or "https://himalayas.app/jobs/api"
        cursor: str | None = None
        while len(jobs) < spec.max_jobs:
            params: dict[str, object] = {"limit": 20}
            if cursor:
                params["cursor"] = cursor
            sep = "&" if "?" in base else "?"
            payload = client.get_json(f"{base}{sep}{urlencode(params)}")
            batch = payload.get("jobs", []) if isinstance(payload, dict) else []
            if not isinstance(batch, list):
                raise ValueError("Himalayas payload jobs must be a list")
            jobs.extend(item for item in batch if isinstance(item, dict))
            cursor = clean_text(payload.get("nextCursor")) if isinstance(payload, dict) else None
            if not cursor or not batch:
                break
            time.sleep(0.5)
        return jobs[: spec.max_jobs]

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        title = clean_text(record.get("title"))
        url = clean_text(record.get("applicationLink"))
        if not title or not url:
            return None
        restrictions = record.get("locationRestrictions") if isinstance(record.get("locationRestrictions"), list) else []
        restriction_names = [name for name in (_restriction_name(item) for item in restrictions) if name]
        location = ", ".join(restriction_names) or "Worldwide"
        salary = None
        if record.get("minSalary") is not None or record.get("maxSalary") is not None:
            salary = {
                "min": record.get("minSalary"),
                "max": record.get("maxSalary"),
                "currency": clean_text(record.get("currency")),
                "period": clean_text(record.get("salaryPeriod")),
            }
        query = clean_text(spec.options.get("query")) if isinstance(spec.options, dict) else None
        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, record.get("guid")),
            "source_instance": spec.instance_id,
            "source_url": spec.endpoint or ("https://himalayas.app/jobs/api/search" if query else "https://himalayas.app/jobs/api"),
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
                "location_restriction_names": restriction_names,
                "timezone_restrictions": record.get("timezoneRestrictions"),
                "categories": record.get("categories"),
                "discovery_query": query,
            },
        }
