from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


def _label(value: Any) -> str | None:
    if isinstance(value, dict):
        return clean_text(value.get("label") or value.get("name") or value.get("id"))
    return clean_text(value)


def _location(value: Any) -> str | None:
    if not isinstance(value, dict):
        return clean_text(value)
    parts = [clean_text(value.get("city")), clean_text(value.get("region")), clean_text(value.get("country"))]
    return ", ".join(part for part in parts if part) or None


def _sections_text(job_ad: Any) -> str | None:
    if not isinstance(job_ad, dict):
        return None
    sections = job_ad.get("sections")
    if not isinstance(sections, dict):
        return None
    texts: list[str] = []
    for section in sections.values():
        if isinstance(section, dict):
            text = html_to_text(section.get("text"))
            if text:
                texts.append(text)
    return "\n\n".join(texts) or None


class SmartRecruitersAdapter(Adapter):
    name = "smartrecruiters"

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        limit = min(100, max(1, int(spec.options.get("page_size", 100))))
        base = spec.endpoint or f"https://api.smartrecruiters.com/v1/companies/{quote(spec.account)}/postings"
        jobs: list[dict[str, Any]] = []
        offset = 0
        while len(jobs) < spec.max_jobs:
            params = urlencode({"limit": limit, "offset": offset, "destination": "PUBLIC"})
            payload = client.get_json(f"{base}?{params}")
            if not isinstance(payload, dict):
                raise ValueError("SmartRecruiters payload must be an object")
            rows = payload.get("content") or payload.get("postings") or []
            if not isinstance(rows, list):
                raise ValueError("SmartRecruiters postings must be a list")
            page = [row for row in rows if isinstance(row, dict)]
            jobs.extend(page)
            total = payload.get("totalFound") or payload.get("total")
            if len(page) < limit or (isinstance(total, int) and len(jobs) >= total):
                break
            offset += len(page)
            if offset >= spec.max_jobs:
                break
        return jobs[: spec.max_jobs]

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        title = clean_text(record.get("name") or record.get("title"))
        job_id = record.get("id") or record.get("uuid")
        if not title or not job_id:
            return None
        company = record.get("company") if isinstance(record.get("company"), dict) else {}
        location_obj = record.get("location") if isinstance(record.get("location"), dict) else {}
        source_ref = clean_text(record.get("ref"))
        apply_url = clean_text(record.get("applyUrl"))
        canonical = apply_url
        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, job_id),
            "source_instance": spec.instance_id,
            "source_url": source_ref or spec.endpoint or f"smartrecruiters://{spec.account}",
            "canonical_url": canonical,
            "url": canonical,
            "employer": spec.employer or clean_text(company.get("name")) or spec.account,
            "title": title,
            "location": _location(record.get("location")),
            "description": _sections_text(record.get("jobAd")),
            "published_at": clean_text(record.get("releasedDate") or record.get("publicationDate")),
            "updated_at": clean_text(record.get("updatedDate")),
            "valid_through": None,
            "employment_type": _label(record.get("typeOfEmployment") or record.get("employmentType")),
            "salary": None,
            "listing_language": spec.listing_language,
            "apply_url": apply_url,
            "remote": location_obj.get("remote") if isinstance(location_obj.get("remote"), bool) else None,
            "workplace_type": clean_text(record.get("workplaceType")),
            "source_metadata": {
                "provider": "smartrecruiters",
                "provider_job_id": job_id,
                "company_identifier": company.get("identifier") or spec.account,
                "department": _label(record.get("department")),
                "location": location_obj,
                "detail_ref": source_ref,
                "job_ad_id": record.get("jobAdId"),
            },
        }
