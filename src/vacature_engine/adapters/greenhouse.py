from __future__ import annotations

import re
from html import unescape
from urllib.parse import quote

from ..models import JobRecord
from .base import AdapterRegistry, BaseAdapter

_TAGS = re.compile(r"<[^>]+>")


def _plain(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", unescape(_TAGS.sub(" ", value))).strip() or None


@AdapterRegistry.register
class GreenhouseAdapter(BaseAdapter):
    source = "greenhouse"

    def fetch(self) -> list[JobRecord]:
        token = quote(self.slug, safe="")
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
        payload = self.client.get_json(url, allowed_hosts={"boards-api.greenhouse.io"})
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise ValueError("greenhouse payload missing jobs[]")
        result: list[JobRecord] = []
        for item in jobs:
            if not isinstance(item, dict):
                continue
            if "internal_job_id" in item and item.get("internal_job_id") is None:
                continue
            first_published = str(item.get("first_published") or "").strip() or None
            updated_at = str(item.get("updated_at") or "").strip() or None
            result.append(
                JobRecord(
                    source=self.source,
                    source_job_id=str(item.get("id", "")),
                    title=str(item.get("title", "")).strip(),
                    employer=self.slug,
                    job_url=str(item.get("absolute_url", "")).strip(),
                    location=(item.get("location") or {}).get("name")
                    if isinstance(item.get("location"), dict)
                    else None,
                    description=_plain(item.get("content")),
                    posted_at=first_published,
                    source_date=updated_at,
                    source_date_semantics="updated_at" if updated_at else None,
                    raw={
                        "first_published": item.get("first_published"),
                        "updated_at": item.get("updated_at"),
                        "application_deadline": item.get("application_deadline"),
                        "metadata": item.get("metadata"),
                    },
                )
            )
        return [j for j in result if j.source_job_id and j.title and j.job_url]
