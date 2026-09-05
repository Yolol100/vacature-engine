from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text

_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,127}$")


def _location_label(record: dict[str, Any]) -> str | None:
    location = record.get("location")
    if isinstance(location, dict):
        primary = clean_text(location.get("location_str"))
        if primary:
            return primary
        parts = [clean_text(location.get(key)) for key in ("city", "region", "country")]
        compact = [part for part in parts if part]
        if compact:
            return ", ".join(compact)
    elif isinstance(location, str):
        return clean_text(location)

    labels: list[str] = []
    locations = record.get("locations")
    if isinstance(locations, list):
        for entry in locations:
            if not isinstance(entry, dict):
                continue
            parts = [clean_text(entry.get(key)) for key in ("city", "state_code", "country_name")]
            label = ", ".join(part for part in parts if part)
            if label and label not in labels:
                labels.append(label)
    return " / ".join(labels) or None


def _remote(record: dict[str, Any], location_label: str | None) -> bool | None:
    location = record.get("location")
    if isinstance(location, dict):
        if location.get("telecommuting") is True:
            return True
        workplace = clean_text(location.get("workplace_type"))
        if workplace and workplace.casefold() == "remote":
            return True
    locations = record.get("locations")
    if isinstance(locations, list):
        for entry in locations:
            if not isinstance(entry, dict):
                continue
            if entry.get("telecommuting") is True:
                return True
            workplace = clean_text(entry.get("workplace_type"))
            if workplace and workplace.casefold() == "remote":
                return True
    if location_label and "remote" in location_label.casefold():
        return True
    return None


class WorkableAdapter(Adapter):
    """Read Workable's public careers/widget JSON endpoint without credentials."""

    name = "workable"

    def _endpoint(self, spec: SourceSpec) -> str:
        if spec.endpoint:
            return spec.endpoint
        if not _ACCOUNT_RE.fullmatch(spec.account):
            raise ValueError("Workable account must be a safe slug when endpoint is omitted")
        return f"https://www.workable.com/api/accounts/{quote(spec.account)}?details=true"

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        payload = client.get_json(self._endpoint(spec))
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        if not isinstance(jobs, list):
            raise ValueError("Workable payload jobs must be a list")
        return [job for job in jobs if isinstance(job, dict)][: spec.max_jobs]

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        title = clean_text(record.get("title"))
        job_id = clean_text(record.get("id") or record.get("shortcode"), max_chars=1000)
        url = clean_text(record.get("url") or record.get("shortlink"))
        if not title or not job_id or not url:
            return None

        published_on = clean_text(record.get("published_on") or record.get("created_at"))
        location_label = _location_label(record)
        is_remote = _remote(record, location_label)

        description = clean_text(record.get("description"))
        full_description = html_to_text(record.get("full_description"))
        if full_description and full_description != description:
            description = "\n\n".join(part for part in (description, full_description) if part)

        salary_raw = record.get("salary")
        salary = None
        if isinstance(salary_raw, dict):
            salary = {
                "min": salary_raw.get("salary_from"),
                "max": salary_raw.get("salary_to"),
                "currency": clean_text(salary_raw.get("salary_currency"), max_chars=16),
            }
            if not any(value is not None for value in salary.values()):
                salary = None

        location_obj = record.get("location") if isinstance(record.get("location"), dict) else {}
        workplace_type = clean_text(location_obj.get("workplace_type"))
        if not workplace_type and is_remote:
            workplace_type = "remote"

        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, job_id),
            "source_instance": spec.instance_id,
            "source_url": self._endpoint(spec),
            "canonical_url": url,
            "url": url,
            "employer": spec.employer or spec.account,
            "title": title,
            "location": location_label,
            "description": description,
            "published_at": published_on,
            "updated_at": clean_text(record.get("updated_at")),
            "valid_through": None,
            "employment_type": clean_text(record.get("employment_type") or record.get("type")),
            "salary": salary,
            "listing_language": spec.listing_language,
            "apply_url": clean_text(record.get("application_url")) or url,
            "remote": is_remote,
            "workplace_type": workplace_type,
            "source_metadata": {
                "provider": "workable",
                "provider_job_id": job_id,
                "shortcode": record.get("shortcode"),
                "department": record.get("department"),
                "experience": record.get("experience"),
                "locations": record.get("locations"),
            },
        }
