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
        if not isinstance(payload, dict) or "jobs" not in payload:
            raise ValueError("Greenhouse response is missing the jobs collection")
        jobs = payload["jobs"]
        if not isinstance(jobs, list):
            raise ValueError("Greenhouse payload jobs must be a list")
        jobs = jobs[: spec.max_jobs]
        # The public list may omit first_published even when the official
        # individual job endpoint exposes it.  Enrich only relevant roles and
        # only when explicitly enabled, with a strict request budget.
        detail_limit = spec.options.get("original_date_detail_limit", 0)
        if (type(detail_limit) is not int or not 0 <= detail_limit <= 20):
            raise ValueError("Greenhouse original_date_detail_limit must be 0..20")
        relevant_terms = ("wordpress", "woocommerce", "elementor",
                          "gutenberg", "php", "frontend", "front-end",
                          "web developer", "website")
        checked = 0
        for index, row in enumerate(jobs):
            if checked >= detail_limit:
                break
            if not isinstance(row, dict) or row.get("first_published"):
                continue
            title = str(row.get("title") or "").casefold()
            job_id = row.get("id")
            if not any(term in title for term in relevant_terms):
                continue
            if not isinstance(job_id, (str, int)) or not str(job_id).strip():
                continue
            checked += 1
            endpoint = (f"https://boards-api.greenhouse.io/v1/boards/"
                        f"{quote(spec.account, safe='')}/jobs/{quote(str(job_id), safe='')}")
            try:
                detail = client.get_json(endpoint)
            except Exception:
                # A detail failure is unknown freshness, never a closed job.
                continue
            if (isinstance(detail, dict) and
                    str(detail.get("id")) == str(job_id) and
                    detail.get("first_published")):
                enriched = dict(row)
                enriched["first_published"] = detail["first_published"]
                enriched["_first_published_evidence_source"] = "official_job_detail"
                jobs[index] = enriched
        return jobs

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
            "published_at": clean_text(record.get("first_published")),
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
                "first_published_at": clean_text(record.get("first_published")),
                "date_semantics": "first_published_when_present",
                "first_published_evidence_source": (
                    record.get("_first_published_evidence_source")
                    or ("official_job_list" if record.get("first_published") else None)
                ),
                "employer_metadata": record.get("metadata"),
                "departments": record.get("departments"),
                "offices": record.get("offices"),
            },
        }
