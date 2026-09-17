from __future__ import annotations

from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

from .base import Adapter, source_job_id
from ..http import FetchError
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def _rss_fields(item: ET.Element) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for child in list(item):
        key = _local_name(child.tag)
        text = clean_text("".join(child.itertext()))
        if text:
            values.setdefault(key, []).append(text)
    return values


def _first(values: dict[str, list[str]], *keys: str) -> str | None:
    for key in keys:
        rows = values.get(key.casefold()) or []
        if rows:
            return rows[0]
    return None


def _rss_pubdate(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return clean_text(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _rss_record(item: ET.Element) -> dict[str, Any] | None:
    values = _rss_fields(item)
    url = _first(values, "link")
    raw_title = _first(values, "title")
    if not url or not raw_title:
        return None

    employer = _first(values, "company", "author")
    title = raw_title
    if not employer and ": " in raw_title:
        possible_employer, possible_title = raw_title.split(": ", 1)
        employer = clean_text(possible_employer)
        title = clean_text(possible_title) or raw_title

    return {
        "id": _first(values, "guid") or url,
        "url": url,
        "jobTitle": title,
        "companyName": employer,
        "jobGeo": _first(values, "region", "location") or "Remote",
        "jobDescription": _first(values, "description", "encoded", "content"),
        "pubDate": _rss_pubdate(_first(values, "pubdate", "published")),
        "jobType": values.get("category", []),
        "_jobicy_transport": "rss",
    }


class JobicyAdapter(Adapter):
    name = "jobicy"

    def _rss_fallback(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        options = spec.options if isinstance(spec.options, dict) else {}
        endpoint = clean_text(options.get("rss_fallback_url")) or "https://jobicy.com/jobs/feed"
        xml = client.get_text(endpoint, headers={"Accept": "application/rss+xml,application/xml,text/xml;q=0.9"})
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise ValueError(f"Jobicy RSS is malformed: {exc}") from exc
        records: list[dict[str, Any]] = []
        for item in root.iter():
            if _local_name(item.tag) != "item":
                continue
            record = _rss_record(item)
            if record:
                records.append(record)
            if len(records) >= spec.max_jobs:
                break
        return records

    def _filter_explicitly_closed(self, client: Any, records: list[dict[str, Any]], spec: SourceSpec) -> list[dict[str, Any]]:
        options = spec.options if isinstance(spec.options, dict) else {}
        if not bool(options.get("head_validate")):
            return records
        kept: list[dict[str, Any]] = []
        for record in records:
            url = clean_text(record.get("url"))
            if not url:
                kept.append(record)
                continue
            try:
                status = int(client.head_status(url))
            except (FetchError, AttributeError, TypeError, ValueError):
                kept.append(record)
                continue
            record = dict(record)
            record["_jobicy_head_status"] = status
            if status in {404, 410}:
                continue
            kept.append(record)
        return kept

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
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
        try:
            payload = client.get_json(f"{base}{sep}{urlencode(params)}")
            jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
            if not isinstance(jobs, list):
                raise ValueError("Jobicy payload jobs must be a list")
            records = []
            for item in jobs:
                if isinstance(item, dict):
                    row = dict(item)
                    row["_jobicy_transport"] = "rest"
                    records.append(row)
        except (FetchError, ValueError):
            records = self._rss_fallback(client, spec)
        return self._filter_explicitly_closed(client, records[: spec.max_jobs], spec)

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
        tag = clean_text(spec.options.get("tag")) if isinstance(spec.options, dict) else None
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
                "discovery_tag": tag,
                "transport": clean_text(record.get("_jobicy_transport")) or "rest",
                "head_status": record.get("_jobicy_head_status"),
                "attribution_required": True,
                "canonical_verification_required": True,
            },
        }
