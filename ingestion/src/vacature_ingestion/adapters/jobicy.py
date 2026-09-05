from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


class JobicyAdapter(Adapter):
    name = "jobicy"

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        base = spec.endpoint or "https://jobicy.com/api/v2/remote-jobs"
        count = min(max(1, spec.max_jobs), 200)
        sep = "&" if "?" in base else "?"
        payload = client.get_json(f"{base}{sep}{urlencode({'count': count})}")
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        if not isinstance(jobs, list):
            raise ValueError("Jobicy payload jobs must be a list")
        return [item for item in jobs if isinstance(item, dict)][: spec.max_jobs]

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        title = clean_text(record.get("jobTitle"))
        url = clean_text(record.get("url"))
        if not title or not url:
            return None
        salary = None
        if record.get("salaryMin") is not None or record.get("salaryMax") is not None:
            salary = {
                "min": record.get("salaryMin"),
                "max": record.get("salaryMax"),
                "currency": clean_text(record.get("salaryCurrency")),
                "period": None,
            }
        job_type = record.get("jobType")
        if isinstance(job_type, list):
            employment_type = ", ".join(clean_text(x) for x in job_type if clean_text(x)) or None
        else:
            employment_type = clean_text(job_type)
        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, record.get("id")),
            "source_instance": spec.instance_id,
            "source_url": spec.endpoint or "https://jobicy.com/api/v2/remote-jobs",
            "canonical_url": url,
            "url": url,
            "employer": clean_text(record.get("companyName")),
            "title": title,
            "location": clean_text(record.get("jobGeo")) or "Remote",
            "description": html_to_text(record.get("jobDescription")),
            "published_at": clean_text(record.get("pubDate")),
            "updated_at": None,
            "valid_through": None,
            "employment_type": employment_type,
            "salary": salary,
            "listing_language": spec.listing_language,
            "apply_url": url,
            "remote": True,
            "workplace_type": "remote",
            "source_metadata": {
                "provider": "jobicy",
                "provider_job_id": record.get("id"),
                "industry": record.get("jobIndustry"),
                "level": record.get("jobLevel"),
            },
        }
