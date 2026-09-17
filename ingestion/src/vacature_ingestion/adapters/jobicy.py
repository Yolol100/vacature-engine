from __future__ import annotations

from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_text(element: ET.Element, *names: str) -> str | None:
    wanted = set(names)
    for child in element.iter():
        if _local_name(child.tag) in wanted:
            value = clean_text(child.text)
            if value:
                return value
    return None


def _rss_date(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return parsedate_to_datetime(text).isoformat()
    except (TypeError, ValueError, OverflowError):
        return text


class JobicyAdapter(Adapter):
    name = "jobicy"

    def _fetch_api(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        base = spec.endpoint or "https://jobicy.com/api/v2/remote-jobs"
        count = min(max(1, spec.max_jobs), 200)
        params: dict[str, object] = {"count": count}
        if isinstance(spec.options, dict):
            tag = clean_text(spec.options.get("tag"))
            industry = clean_text(spec.options.get("industry"))
            geo = clean_text(spec.options.get("geo"))
            if tag:
                params["tag"] = tag
            if industry:
                params["industry"] = industry
            if geo:
                params["geo"] = geo
        sep = "&" if "?" in base else "?"
        endpoint = f"{base}{sep}{urlencode(params)}"
        payload = client.get_json(endpoint)
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        if not isinstance(jobs, list):
            raise ValueError("Jobicy payload jobs must be a list")
        rows = [item for item in jobs if isinstance(item, dict)][: spec.max_jobs]
        for item in rows:
            item.setdefault("_jobicy_mode", "api")
            item.setdefault("_source_endpoint", base)
        return rows

    def _fetch_rss(self, client: Any, spec: SourceSpec, rss_url: str) -> list[dict[str, Any]]:
        xml_text = client.get_text(
            rss_url,
            headers={"Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.5"},
        )
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise ValueError(f"invalid Jobicy RSS: {exc}") from exc

        rows: list[dict[str, Any]] = []
        for item in root.iter():
            if _local_name(item.tag) != "item":
                continue
            url = _first_text(item, "link")
            title = _first_text(item, "title")
            if not url or not title:
                continue
            rows.append(
                {
                    "id": _first_text(item, "guid") or url,
                    "url": url,
                    "jobTitle": title,
                    "companyName": _first_text(item, "companyName", "company", "creator", "author"),
                    "jobGeo": _first_text(item, "jobGeo", "location"),
                    "jobDescription": _first_text(item, "description", "encoded"),
                    "pubDate": _rss_date(_first_text(item, "pubDate", "date")),
                    "jobType": _first_text(item, "jobType", "type"),
                    "_jobicy_mode": "rss_fallback",
                    "_source_endpoint": rss_url,
                }
            )
            if len(rows) >= spec.max_jobs:
                break

        tag = clean_text(spec.options.get("tag")) if isinstance(spec.options, dict) else None
        if tag:
            needle = tag.casefold()
            rows = [
                row
                for row in rows
                if needle
                in " ".join(
                    value
                    for value in (
                        clean_text(row.get("jobTitle")),
                        clean_text(row.get("companyName")),
                        html_to_text(row.get("jobDescription")),
                    )
                    if value
                ).casefold()
            ]
        return rows[: spec.max_jobs]

    def _filter_closed_head(self, client: Any, rows: list[dict[str, Any]], spec: SourceSpec) -> list[dict[str, Any]]:
        options = spec.options if isinstance(spec.options, dict) else {}
        if not options.get("verify_active_head"):
            return rows
        head_status = getattr(client, "head_status", None)
        if not callable(head_status):
            return rows

        active: list[dict[str, Any]] = []
        for row in rows:
            url = clean_text(row.get("url"))
            if not url:
                active.append(row)
                continue
            try:
                status = int(head_status(url))
                row["_head_status"] = status
                if status in {404, 410}:
                    continue
            except Exception as exc:
                row["_head_error"] = type(exc).__name__
            active.append(row)
        return active

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        options = spec.options if isinstance(spec.options, dict) else {}
        try:
            rows = self._fetch_api(client, spec)
        except Exception:
            rss_url = clean_text(options.get("rss_fallback_url"))
            if not rss_url:
                raise
            rows = self._fetch_rss(client, spec, rss_url)
        return self._filter_closed_head(client, rows, spec)

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
                "period": clean_text(record.get("salaryPeriod")),
            }
        job_type = record.get("jobType")
        if isinstance(job_type, list):
            employment_type = ", ".join(clean_text(x) for x in job_type if clean_text(x)) or None
        else:
            employment_type = clean_text(job_type)

        options = spec.options if isinstance(spec.options, dict) else {}
        tag = clean_text(options.get("tag"))
        metadata = {
            "provider": "jobicy",
            "provider_job_id": record.get("id"),
            "industry": record.get("jobIndustry"),
            "level": record.get("jobLevel"),
            "discovery_tag": tag,
            "discovery_mode": clean_text(record.get("_jobicy_mode")) or "api",
            "attribution_required": bool(options.get("attribution_required", True)),
        }
        if record.get("_head_status") is not None:
            metadata["availability_head_status"] = record.get("_head_status")
        if record.get("_head_error"):
            metadata["availability_head_error"] = record.get("_head_error")

        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, record.get("id")),
            "source_instance": spec.instance_id,
            "source_url": clean_text(record.get("_source_endpoint")) or spec.endpoint or "https://jobicy.com/api/v2/remote-jobs",
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
            "source_metadata": metadata,
        }
