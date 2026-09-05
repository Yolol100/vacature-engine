from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlencode
from xml.etree import ElementTree as ET

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, html_to_text

_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")


def _text(node: ET.Element, path: str) -> str | None:
    child = node.find(path)
    return clean_text(child.text if child is not None else None)


def _description_sections(position: ET.Element) -> list[dict[str, str | None]]:
    sections: list[dict[str, str | None]] = []
    for section in position.findall("./jobDescriptions/jobDescription"):
        name = _text(section, "name")
        value_node = section.find("value")
        value = value_node.text if value_node is not None else None
        sections.append({"name": name, "value": value})
    return sections


def _description_text(sections: Any) -> str | None:
    if not isinstance(sections, list):
        return None
    parts: list[str] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        heading = clean_text(section.get("name"))
        body = html_to_text(section.get("value"))
        if heading and body:
            parts.append(f"{heading}\n{body}")
        elif body:
            parts.append(body)
    return "\n\n".join(parts) or None


class PersonioAdapter(Adapter):
    """Read Personio's public XML career feed without credentials."""

    name = "personio"

    def _feed_url(self, spec: SourceSpec) -> str:
        if spec.endpoint:
            return spec.endpoint
        if not _ACCOUNT_RE.fullmatch(spec.account):
            raise ValueError("Personio account must be a hostname-safe slug when endpoint is omitted")
        language = clean_text(spec.options.get("language") or spec.listing_language, max_chars=16) or "en"
        return f"https://{spec.account}.jobs.personio.com/xml?{urlencode({'language': language})}"

    def fetch(self, client: Any, spec: SourceSpec) -> list[dict[str, Any]]:
        feed_url = self._feed_url(spec)
        xml_text = client.get_text(
            feed_url,
            headers={"Accept": "application/xml,text/xml;q=0.9,*/*;q=0.1"},
        )
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise ValueError(f"Personio XML is malformed: {exc}") from exc

        rows: list[dict[str, Any]] = []
        for position in root.findall(".//position"):
            row: dict[str, Any] = {
                "id": _text(position, "id"),
                "subcompany": _text(position, "subcompany"),
                "office": _text(position, "office"),
                "department": _text(position, "department"),
                "recruitingCategory": _text(position, "recruitingCategory"),
                "name": _text(position, "name"),
                "employmentType": _text(position, "employmentType"),
                "seniority": _text(position, "seniority"),
                "schedule": _text(position, "schedule"),
                "yearsOfExperience": _text(position, "yearsOfExperience"),
                "keywords": _text(position, "keywords"),
                "occupation": _text(position, "occupation"),
                "occupationCategory": _text(position, "occupationCategory"),
                "createdAt": _text(position, "createdAt"),
                "jobDescriptions": _description_sections(position),
            }
            rows.append(row)
            if len(rows) >= spec.max_jobs:
                break
        return rows

    def normalize_record(self, record: dict[str, Any], spec: SourceSpec, now: str) -> dict[str, Any] | None:
        job_id = clean_text(record.get("id"), max_chars=1000)
        title = clean_text(record.get("name"))
        if not job_id or not title:
            return None

        career_base = clean_text(spec.options.get("career_base_url"))
        if not career_base:
            if not _ACCOUNT_RE.fullmatch(spec.account):
                return None
            career_base = f"https://{spec.account}.jobs.personio.com"
        canonical = f"{career_base.rstrip('/')}/job/{quote(job_id, safe='')}"

        office = clean_text(record.get("office"))
        is_remote = True if office and "remote" in office.casefold() else None
        employment_type = clean_text(record.get("schedule") or record.get("employmentType"))
        listing_language = spec.listing_language or clean_text(spec.options.get("language"), max_chars=16)

        return {
            "source_id": spec.source_id,
            "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, job_id),
            "source_instance": spec.instance_id,
            "source_url": self._feed_url(spec),
            "canonical_url": canonical,
            "url": canonical,
            "employer": spec.employer or clean_text(record.get("subcompany")) or spec.account,
            "title": title,
            "location": office,
            "description": _description_text(record.get("jobDescriptions")),
            "published_at": clean_text(record.get("createdAt")),
            "updated_at": None,
            "valid_through": None,
            "employment_type": employment_type,
            "salary": None,
            "listing_language": listing_language,
            "apply_url": canonical,
            "remote": is_remote,
            "workplace_type": "remote" if is_remote else None,
            "source_metadata": {
                "provider": "personio",
                "provider_job_id": job_id,
                "subcompany": record.get("subcompany"),
                "department": record.get("department"),
                "recruiting_category": record.get("recruitingCategory"),
                "employment_type": record.get("employmentType"),
                "schedule": record.get("schedule"),
                "seniority": record.get("seniority"),
                "years_of_experience": record.get("yearsOfExperience"),
                "keywords": record.get("keywords"),
                "occupation": record.get("occupation"),
                "occupation_category": record.get("occupationCategory"),
            },
        }
