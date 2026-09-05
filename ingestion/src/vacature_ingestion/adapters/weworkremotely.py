from __future__ import annotations

from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any
import xml.etree.ElementTree as ET

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def _item_fields(item: ET.Element) -> dict[str, list[str]]:
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


def _published_at(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return clean_text(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


class WeWorkRemotelyAdapter(Adapter):
    name = "weworkremotely"

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        endpoint = spec.endpoint or "https://weworkremotely.com/categories/remote-programming-jobs.rss"
        xml = client.get_text(endpoint, headers={"Accept": "application/rss+xml,application/xml,text/xml;q=0.9"})
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise ValueError(f"We Work Remotely RSS is malformed: {exc}") from exc
        records: list[dict[str, Any]] = []
        for item in root.iter():
            if _local_name(item.tag) != "item":
                continue
            records.append({"_rss_fields": _item_fields(item)})
            if len(records) >= spec.max_jobs:
                break
        return records

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        values = record.get("_rss_fields")
        if not isinstance(values, dict):
            return None
        raw_title = _first(values, "title")
        url = _first(values, "link", "guid")
        if not raw_title or not url:
            return None

        employer = _first(values, "company")
        title = raw_title
        if not employer and ": " in raw_title:
            possible_employer, possible_title = raw_title.split(": ", 1)
            employer = clean_text(possible_employer)
            title = clean_text(possible_title) or raw_title

        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, _first(values, "guid") or url),
            "source_instance": spec.instance_id,
            "source_url": spec.endpoint or "https://weworkremotely.com/categories/remote-programming-jobs.rss",
            "canonical_url": url,
            "url": url,
            "employer": employer,
            "title": title,
            "location": _first(values, "region", "location") or "Remote",
            "description": html_to_text(_first(values, "description", "content")),
            "published_at": _published_at(_first(values, "pubdate", "published")),
            "updated_at": None,
            "valid_through": None,
            "employment_type": _first(values, "type", "jobtype"),
            "salary": None,
            "listing_language": spec.listing_language,
            "apply_url": url,
            "remote": True,
            "workplace_type": "remote",
            "source_metadata": {
                "provider": "weworkremotely",
                "categories": values.get("category", []),
                "attribution_required": True,
                "canonical_verification_required": True,
            },
        }
