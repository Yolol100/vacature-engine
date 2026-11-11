"""Public official WordPress Jobs category RSS, for discovery only.

The feed publication timestamp is NOT independently verified employer-original
publication. Each role remains unverified until checked on its exact employer
application page. No requests to job links are made here.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from .base import Adapter, source_job_id
from .weworkremotely import _first, _item_fields, _local_name, _published_at
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


_FEEDS = {
    "development": "https://jobs.wordpress.net/job_category/development/feed/",
    "design": "https://jobs.wordpress.net/job_category/design/feed/",
}


class WordPressJobsAdapter(Adapter):
    name = "wordpressjobs"
    complete_snapshot = False  # Category feeds cannot establish absence/closure.

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        endpoint = _FEEDS.get(spec.account)
        if (spec.source_id != "wordpress-jobs"
                or spec.source_type != "wordpress_discovery"
                or not endpoint or spec.endpoint != endpoint):
            raise ValueError("WordPress Jobs feed configuration is not registered/approved")
        xml = client.get_text(
            endpoint,
            headers={"Accept": "application/rss+xml,application/xml,text/xml;q=0.9"},
        )
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            raise ValueError("WordPress Jobs RSS is malformed") from exc
        if _local_name(root.tag) != "rss":
            raise ValueError("WordPress Jobs RSS root is missing")
        records: list[dict[str, Any]] = []
        for item in root.iter():
            if _local_name(item.tag) != "item":
                continue
            records.append({"_rss_fields": _item_fields(item)})
            if len(records) >= min(spec.max_jobs, 80):
                break
        return records

    def normalize_record(
        self, record: dict[str, Any], spec: SourceSpec, now: str
    ) -> dict[str, Any] | None:
        fields = record.get("_rss_fields")
        if not isinstance(fields, dict):
            return None
        title = _first(fields, "title")
        url = _first(fields, "link")
        if not title or not url:
            return None
        # A curated RSS feed may point to a position at a different employer.
        # The feed URL never verifies that the employer has an open ATS route.
        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, _first(fields, "guid") or url),
            "source_instance": spec.instance_id,
            "source_url": spec.endpoint,
            "canonical_url": url,
            "url": url,
            "apply_url": url,
            "employer": _first(fields, "company", "company_name", "employer"),
            "title": title,
            "location": _first(fields, "job_location", "location", "region"),
            "description": html_to_text(_first(fields, "description", "content")),
            "published_at": _published_at(_first(fields, "pubdate", "published")),
            "updated_at": None,
            "valid_through": None,
            "employment_type": _first(fields, "type", "jobtype"),
            "salary": None,
            "listing_language": spec.listing_language,
            "remote": None,
            "workplace_type": None,
            "source_metadata": {
                "provider": "wordpressjobs",
                "categories": fields.get("category", []),
                "original_employer_publication_unverified": True,
                "remote_from_netherlands_unverified": True,
            },
        }
