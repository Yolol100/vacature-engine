from __future__ import annotations

from html import unescape
import re
from urllib.parse import quote

from .base import AdapterRegistry, BaseAdapter
from ..models import JobRecord

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
            result.append(
                JobRecord(
                    source=self.source,
                    source_job_id=str(item.get("id", "")),
                    title=str(item.get("title", "")).strip(),
                    employer=self.slug,
                    job_url=str(item.get("absolute_url", "")).strip(),
                    location=(item.get("location") or {}).get("name") if isinstance(item.get("location"), dict) else None,
                    description=_plain(item.get("content")),
                    posted_at=None,
                    raw={"updated_at": item.get("updated_at"), "metadata": item.get("metadata")},
                )
            )
        return [j for j in result if j.source_job_id and j.title and j.job_url]
