from __future__ import annotations

import json
import re
from typing import Any, Iterable

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text

_SCRIPT_RE = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def _iter_objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _iter_objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_objects(item)


def _is_job_posting(value: dict[str, Any]) -> bool:
    raw = value.get("@type")
    if isinstance(raw, str):
        return raw.casefold() == "jobposting"
    if isinstance(raw, list):
        return any(isinstance(item, str) and item.casefold() == "jobposting" for item in raw)
    return False


def _address_text(value: Any) -> str | None:
    if not isinstance(value, dict):
        return clean_text(value)
    address = value.get("address") if isinstance(value.get("address"), dict) else value
    parts = [
        clean_text(address.get("addressLocality")),
        clean_text(address.get("addressRegion")),
        clean_text(address.get("addressCountry")),
    ]
    return ", ".join(part for part in parts if part) or None


def _location_text(value: Any) -> str | None:
    if isinstance(value, list):
        parts = [_address_text(item) for item in value]
        return "; ".join(part for part in parts if part) or None
    return _address_text(value)


def _identifier(value: Any) -> str | None:
    if isinstance(value, dict):
        return clean_text(value.get("value") or value.get("name"))
    return clean_text(value)


class JsonLdAdapter(Adapter):
    name = "jsonld"

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        urls = spec.options.get("urls") if isinstance(spec.options, dict) else None
        if not isinstance(urls, list) or not urls:
            urls = [spec.endpoint] if spec.endpoint else []
        urls = [str(url).strip() for url in urls if str(url).strip()]
        if not urls:
            raise ValueError("jsonld adapter requires endpoint or options.urls")

        jobs: list[dict[str, Any]] = []
        for url in urls[: spec.max_jobs]:
            html = client.get_text(url, headers={"Accept": "text/html,application/xhtml+xml"})
            found = False
            for match in _SCRIPT_RE.finditer(html):
                raw = match.group(1).strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                for item in _iter_objects(payload):
                    if _is_job_posting(item):
                        copy = dict(item)
                        copy["__source_page_url"] = url
                        jobs.append(copy)
                        found = True
                        if len(jobs) >= spec.max_jobs:
                            return jobs
            if not found and spec.options.get("require_jobposting", True):
                continue
        return jobs

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        title = clean_text(record.get("title"))
        page_url = clean_text(record.get("__source_page_url"))
        url = clean_text(record.get("url")) or page_url
        if not title or not url:
            return None
        organization = record.get("hiringOrganization") if isinstance(record.get("hiringOrganization"), dict) else {}
        job_location_type = clean_text(record.get("jobLocationType"))
        remote = True if job_location_type and "telecommute" in job_location_type.casefold() else None
        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, _identifier(record.get("identifier"))),
            "source_instance": spec.instance_id,
            "source_url": page_url or url,
            "canonical_url": url,
            "url": url,
            "employer": spec.employer or clean_text(organization.get("name")) or spec.account,
            "title": title,
            "location": _location_text(record.get("jobLocation")) or clean_text(record.get("applicantLocationRequirements")),
            "description": html_to_text(record.get("description")),
            "published_at": clean_text(record.get("datePosted")),
            "updated_at": None,
            "valid_through": clean_text(record.get("validThrough")),
            "employment_type": clean_text(record.get("employmentType")),
            "salary": record.get("baseSalary") if isinstance(record.get("baseSalary"), (dict, list)) else None,
            "listing_language": spec.listing_language,
            "apply_url": url,
            "remote": remote,
            "workplace_type": job_location_type,
            "source_metadata": {
                "provider": "jsonld",
                "identifier": record.get("identifier"),
                "applicant_location_requirements": record.get("applicantLocationRequirements"),
                "direct_apply": record.get("directApply"),
            },
        }
