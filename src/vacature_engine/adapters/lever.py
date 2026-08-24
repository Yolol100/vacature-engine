from __future__ import annotations

from datetime import UTC, datetime
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


def _millis_iso(value: object) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(float(value) / 1000, UTC).isoformat()


@AdapterRegistry.register
class LeverAdapter(BaseAdapter):
    source = "lever"

    def __init__(self, slug: str, *, region: str = "global", **kwargs: object) -> None:
        super().__init__(slug, **kwargs)
        if region not in {"global", "eu"}:
            raise ValueError("region must be global or eu")
        self.region = region

    def fetch(self) -> list[JobRecord]:
        host = "api.eu.lever.co" if self.region == "eu" else "api.lever.co"
        url = f"https://{host}/v0/postings/{quote(self.slug, safe='')}?mode=json"
        payload = self.client.get_json(url, allowed_hosts={host})
        if not isinstance(payload, list):
            raise ValueError("lever payload must be a list")
        result: list[JobRecord] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            categories = item.get("categories") if isinstance(item.get("categories"), dict) else {}
            workplace = str(item.get("workplaceType") or "").lower()
            location = categories.get("location")
            is_remote = True if workplace == "remote" else None
            if is_remote is None and isinstance(location, str) and "remote" in location.lower():
                is_remote = True
            result.append(
                JobRecord(
                    source=self.source,
                    source_job_id=str(item.get("id", "")),
                    title=str(item.get("text", "")).strip(),
                    employer=self.slug,
                    job_url=str(item.get("hostedUrl", "")).strip(),
                    apply_url=str(item.get("applyUrl") or "").strip() or None,
                    location=location if isinstance(location, str) else None,
                    is_remote=is_remote,
                    employment_type=categories.get("commitment") if isinstance(categories.get("commitment"), str) else None,
                    department=categories.get("department") if isinstance(categories.get("department"), str) else None,
                    team=categories.get("team") if isinstance(categories.get("team"), str) else None,
                    description=_plain(item.get("descriptionPlain") or item.get("description")),
                    posted_at=_millis_iso(item.get("createdAt")),
                    raw={"workplace_type": item.get("workplaceType"), "categories": categories},
                )
            )
        return [j for j in result if j.source_job_id and j.title and j.job_url]
