"""Official employer RSS for Servebolt. Listings are discovery candidates."""
from __future__ import annotations

import re
from typing import Any
import xml.etree.ElementTree as ET

from .base import Adapter, source_job_id
from .weworkremotely import _first, _item_fields, _local_name, _published_at
from ..models import SourceSpec
from ..normalize import html_to_text


_ENDPOINT = "https://careers.servebolt.com/jobs.rss"
_JOB = re.compile(r"^https://careers\.servebolt\.com/jobs/([1-9]\d*)-[a-z0-9-]+/?$")


class TeamtailorAdapter(Adapter):
    name = "teamtailor"
    complete_snapshot = False

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        if (spec.source_id, spec.source_type, spec.account, spec.endpoint) != (
            "teamtailor", "ats", "servebolt", _ENDPOINT
        ) or spec.options.get("registry_source_id") != "company-servebolt":
            raise ValueError("Teamtailor employer feed is not approved")
        xml = client.get_text(_ENDPOINT, headers={"Accept": "application/rss+xml"})
        if re.search(r"<!DOCTYPE|<!ENTITY", xml, re.IGNORECASE):
            raise ValueError("Unexpected Teamtailor RSS declaration")
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise ValueError("Teamtailor RSS is malformed") from exc
        channel = next((node for node in root if _local_name(node.tag) == "channel"), None)
        if _local_name(root.tag) != "rss" or channel is None:
            raise ValueError("Teamtailor RSS channel missing")
        records = []
        for node in channel:
            if _local_name(node.tag) != "item":
                continue
            if len(records) >= min(spec.max_jobs, 50):
                break
            records.append({"_rss_fields": _item_fields(node)})
        return records

    def normalize_record(
        self, record: dict[str, Any], spec: SourceSpec, now: str
    ) -> dict[str, Any] | None:
        fields = record.get("_rss_fields")
        if not isinstance(fields, dict):
            return None
        title = _first(fields, "title")
        url = _first(fields, "link")
        match = _JOB.fullmatch(url or "")
        if not title or not match:
            return None
        remote_status = (_first(fields, "remotestatus") or "").casefold()
        if remote_status in {"hybrid", "none", "on-site", "on site", "onsite", "temporary"}:
            return None
        remote = remote_status in {"fully", "remote", "fully remote"}
        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, match.group(1)),
            "source_instance": spec.instance_id,
            "source_url": _ENDPOINT,
            "canonical_url": url,
            "url": url,
            "apply_url": url,
            "employer": "Servebolt",
            "title": title,
            "location": "Remote" if remote else None,
            "description": html_to_text(_first(fields, "description")),
            "published_at": None,
            "remote": True if remote else None,
            "workplace_type": "remote" if remote else None,
            "listing_language": spec.listing_language,
            "source_metadata": {
                "provider": "teamtailor",
                "provider_pub_date": _published_at(_first(fields, "pubdate")),
                "original_employer_publication_unverified": True,
                "remote_from_netherlands_unverified": True,
            },
        }
