from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


class AshbyAdapter(Adapter):
    name = "ashby"

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        endpoint = spec.endpoint or f"https://api.ashbyhq.com/posting-api/job-board/{quote(spec.account)}?includeCompensation=true"
        payload = client.get_json(endpoint)
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        if not isinstance(jobs, list):
            raise ValueError("Ashby payload jobs must be a list")
        return jobs[: spec.max_jobs]

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        if record.get("isListed") is False:
            return None
        title = clean_text(record.get("title"))
        url = clean_text(record.get("jobUrl"))
        if not title or not url:
            return None
        compensation = record.get("compensation") if isinstance(record.get("compensation"), dict) else None
        salary = None
        if compensation:
            salary = {
                "summary": compensation.get("scrapeableCompensationSalarySummary") or compensation.get("compensationTierSummary"),
                "components": compensation.get("summaryComponents"),
            }
        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, record.get("id")),
            "source_instance": spec.instance_id,
            "source_url": spec.endpoint or f"ashby://{spec.account}",
            "canonical_url": url,
            "url": url,
            "employer": spec.employer or spec.account,
            "title": title,
            "location": clean_text(record.get("location")),
            "description": clean_text(record.get("descriptionPlain")) or html_to_text(record.get("descriptionHtml")),
            "published_at": clean_text(record.get("publishedAt")),
            "updated_at": None,
            "valid_through": None,
            "employment_type": clean_text(record.get("employmentType")),
            "salary": salary,
            "listing_language": spec.listing_language,
            "apply_url": clean_text(record.get("applyUrl")) or url,
            "remote": record.get("isRemote") if isinstance(record.get("isRemote"), bool) else None,
            "workplace_type": clean_text(record.get("workplaceType")),
            "source_metadata": {
                "provider": "ashby",
                "department": record.get("department"),
                "team": record.get("team"),
                "is_listed": record.get("isListed"),
                "secondary_locations": record.get("secondaryLocations"),
                "address": record.get("address"),
            },
        }
