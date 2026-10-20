from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text


# Only three official, public, read-only feeds. No generic URL fetching.
_HOSTS = {
    "arbeitnow-api": ("www.arbeitnow.com", "https://www.arbeitnow.com/api/job-board-api"),
    "remote-landers-api": ("remotelanders.com", "https://remotelanders.com/api/jobs"),
    "remotejobs-org": ("remotejobs.org", "https://remotejobs.org/api/v1/jobs"),
    "working-nomads": ("www.workingnomads.com", "https://www.workingnomads.com/api/exposed_jobs/"),
}


class PublicFeedsAdapter(Adapter):
    name = "publicfeeds"
    complete_snapshot = False  # PublicFeeds feeds are bounded subsets and searches.

    def can_quarantine_record_error(self, spec: SourceSpec, error: ValueError) -> bool:
        # Preserve the existing Actions bridge's narrow quarantine policy.
        # The rejected URL is never admitted or included in diagnostics.
        return spec.source_id == "arbeitnow-api" and str(error) in {
            "Unexpected public feed job URL: untrusted_host",
            "Unexpected public feed job URL: uk_apex",
            "Unexpected public feed job URL: malformed",
        }

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        if spec.source_id not in _HOSTS or spec.endpoint is not None:
            raise ValueError("Unsupported public feed source contract")
        if spec.source_id == "arbeitnow-api":
            payload = client.get_json(_HOSTS[spec.source_id][1])
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise ValueError("Invalid Arbeitnow response")
            rows = [x for x in payload["data"] if isinstance(x, dict) and x.get("remote") is True]
        elif spec.source_id == "working-nomads":
            payload = client.get_json(_HOSTS[spec.source_id][1])
            if (not isinstance(payload, list) or not payload
                    or not all(isinstance(row, dict) for row in payload)):
                raise ValueError("Invalid Working Nomads response")
            rows = payload
        elif spec.source_id == "remote-landers-api":
            rows = []
            # One small request per relevant discipline. No full catalog sweep.
            for category in ("Engineering", "Design"):
                url = _HOSTS[spec.source_id][1] + "?category=" + category + "&limit=50"
                payload = client.get_json(url)
                if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
                    raise ValueError("Invalid Remote Landers response")
                rows.extend(x for x in payload["jobs"] if isinstance(x, dict))
        else:
            rows = []
            for query in ("wordpress", "automation"):
                url = _HOSTS[spec.source_id][1] + "?q=" + query + "&limit=30&offset=0"
                payload = client.get_json(url)
                if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                    raise ValueError("Invalid RemoteJobs.org response")
                rows.extend(x for x in payload["data"] if isinstance(x, dict))
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            key = str(row.get("id") or row.get("slug") or row.get("url") or "")
            if key and key not in seen:
                seen.add(key)
                unique.append(row)
            if len(unique) >= min(spec.max_jobs, 120):
                break
        return unique

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        source = spec.source_id
        if source == "working-nomads":
            title = clean_text(record.get("title"))
            url = clean_text(record.get("url"))
            if not title or not url:
                return None
            try:
                parts = urlsplit(url)
                valid = (
                    parts.scheme == "https"
                    and parts.hostname == "www.workingnomads.com"
                    and parts.port is None
                    and parts.username is None
                    and parts.password is None
                    and not parts.query
                    and not parts.fragment
                    and re.fullmatch(r"/job/go/[0-9]+/?", parts.path) is not None
                )
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("Unexpected Working Nomads job URL")
            return {
                "source_id": source,
                "source_type": spec.source_type,
                "source_job_id": source_job_id(spec, parts.path.strip("/").split("/")[-1]),
                "source_instance": spec.instance_id,
                "source_url": _HOSTS[source][1],
                "canonical_url": url,
                "url": url,
                "employer": clean_text(record.get("company_name")),
                "title": title,
                "location": clean_text(record.get("location")),
                "description": html_to_text(record.get("description")),
                # The board's pub_date is NOT independently evidenced
                # as the employer's original publication date.
                "published_at": None,
                "updated_at": None,
                "valid_through": None,
                "employment_type": None,
                "salary": None,
                "listing_language": spec.listing_language,
                "apply_url": None,
                "remote": None,
                "workplace_type": None,
                "source_metadata": {
                    "provider": "working-nomads",
                    "provider_pub_date": clean_text(record.get("pub_date")),
                    "category_name": clean_text(record.get("category_name")),
                    "tags": clean_text(record.get("tags")),
                    "attribution_required": True,
                    "canonical_verification_required": True,
                    "original_posting_date_unverified": True,
                    "discovery_only": True,
                },
            }
        if source not in _HOSTS:
            raise ValueError("Unsupported public feed source contract")
        base_host, api_url = _HOSTS[source]
        url = clean_text(record.get("url"))
        title = clean_text(record.get("title"))
        if not url or not title:
            return None
        try:
            target = urlsplit(url)
        except ValueError as error:
            # A malformed authority must be quarantinable without leaking its URL.
            raise ValueError("Unexpected public feed job URL: malformed") from error
        # The official .com feed also links to Arbeitnow's documented UK site.
        allowed_hosts = {base_host, "arbeitnow.com", "www.arbeitnow.co.uk"} if source == "arbeitnow-api" else {base_host}
        # Keep the strict host gate. Distinguish a small, fixed family of
        # failures without echoing provider-controlled URLs to public CI logs.
        if target.scheme != "https" or target.username or target.password:
            raise ValueError("Unexpected public feed job URL: malformed")
        if target.hostname not in allowed_hosts:
            if source == "arbeitnow-api" and target.hostname == "arbeitnow.co.uk":
                raise ValueError("Unexpected public feed job URL: uk_apex")
            raise ValueError("Unexpected public feed job URL: untrusted_host")
        company = record.get("company")
        if isinstance(company, dict):
            company = company.get("name")
        employer = clean_text(record.get("company_name") or company)
        location = clean_text(record.get("location")) or "Remote (location unverified)"
        remote = bool(record.get("remote")) if source == "arbeitnow-api" else True
        if source == "arbeitnow-api" and not remote:
            return None
        return {
            "source_id": source,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, record.get("id") or record.get("slug") or url),
            "source_instance": spec.instance_id,
            "source_url": api_url,
            "canonical_url": url,
            "url": url,
            "employer": employer,
            "title": title,
            "location": location,
            "description": html_to_text(record.get("description")),
            "published_at": clean_text(record.get("posted_at") or record.get("postedDate")),
            "updated_at": None,
            "valid_through": None,
            "employment_type": clean_text(record.get("type")),
            "salary": clean_text(record.get("salary_text") or record.get("salary")),
            "listing_language": spec.listing_language,
            "apply_url": url,
            "remote": remote,
            "workplace_type": "remote" if remote else "unknown",
            "source_metadata": {
                "provider": source,
                "attribution_required": True,
                "canonical_verification_required": True,
                "discovery_only": True,
            },
        }
