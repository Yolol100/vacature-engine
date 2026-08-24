from __future__ import annotations

import re
from html import unescape
from urllib.parse import quote

from ..models import JobRecord
from .base import AdapterRegistry, BaseAdapter

_TAGS = re.compile(r"<[^>]+>")


def _plain(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return re.sub(r"\s+", " ", unescape(_TAGS.sub(" ", value))).strip() or None


def _section_text(detail: dict[str, object]) -> str | None:
    job_ad = detail.get("jobAd")
    if not isinstance(job_ad, dict):
        return None
    sections = job_ad.get("sections")
    if not isinstance(sections, dict):
        return None
    parts: list[str] = []
    for value in sections.values():
        if isinstance(value, dict):
            text = _plain(value.get("text"))
            if text:
                parts.append(text)
    return "\n\n".join(parts) or None


@AdapterRegistry.register
class SmartRecruitersAdapter(BaseAdapter):
    source = "smartrecruiters"

    def __init__(self, slug: str, *, max_pages: int = 50, **kwargs: object) -> None:
        super().__init__(slug, **kwargs)
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 50:
            raise ValueError("max_pages must be an integer between 1 and 50")
        self.max_pages = max_pages

    def _list_postings(self, base: str) -> list[dict[str, object]]:
        limit = 100
        offset = 0
        items: list[dict[str, object]] = []
        for _page in range(self.max_pages):
            payload = self.client.get_json(
                f"{base}?destination=PUBLIC&limit={limit}&offset={offset}",
                allowed_hosts={"api.smartrecruiters.com"},
            )
            content = payload.get("content") if isinstance(payload, dict) else None
            if not isinstance(content, list):
                raise ValueError("smartrecruiters payload missing content[]")
            page_items = [item for item in content if isinstance(item, dict)]
            items.extend(page_items)
            total = payload.get("totalFound") if isinstance(payload, dict) else None
            if len(content) < limit or (isinstance(total, int) and offset + len(content) >= total):
                return items
            offset += limit
        raise ValueError("smartrecruiters pagination exceeded max_pages")

    def fetch(self) -> list[JobRecord]:
        slug = quote(self.slug, safe="")
        base = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
        content = self._list_postings(base)
        result: list[JobRecord] = []
        for item in content:
            posting_id = str(item.get("id") or item.get("uuid") or "")
            detail: dict[str, object] = item
            if posting_id:
                fetched = self.client.get_json(
                    f"{base}/{quote(posting_id, safe='')}",
                    allowed_hosts={"api.smartrecruiters.com"},
                )
                if isinstance(fetched, dict):
                    detail = fetched
            location_obj = detail.get("location") if isinstance(detail.get("location"), dict) else {}
            location_bits = [location_obj.get("city"), location_obj.get("region"), location_obj.get("country")]
            location = ", ".join(str(x) for x in location_bits if x) or None
            department_obj = detail.get("department") if isinstance(detail.get("department"), dict) else {}
            employment_obj = detail.get("typeOfEmployment") if isinstance(detail.get("typeOfEmployment"), dict) else {}
            posting_url = str(
                detail.get("postingUrl")
                or item.get("postingUrl")
                or detail.get("jobAdUrl")
                or item.get("jobAdUrl")
                or detail.get("ref")
                or f"{base}/{posting_id}"
            ).strip()
            released = str(
                detail.get("releasedDate") or item.get("releasedDate") or ""
            ).strip() or None
            result.append(
                JobRecord(
                    source=self.source,
                    source_job_id=posting_id,
                    title=str(detail.get("name") or item.get("name") or "").strip(),
                    employer=self.slug,
                    job_url=posting_url,
                    apply_url=str(detail.get("applyUrl") or item.get("applyUrl") or "").strip() or None,
                    location=location,
                    is_remote=location_obj.get("remote") if isinstance(location_obj.get("remote"), bool) else None,
                    employment_type=str(employment_obj.get("label") or "").strip() or None,
                    department=str(department_obj.get("label") or "").strip() or None,
                    description=_section_text(detail),
                    posted_at=None,
                    source_date=released,
                    source_date_semantics="released_date_not_proven_original" if released else None,
                    raw={
                        "ref": detail.get("ref"),
                        "experience_level": detail.get("experienceLevel"),
                        "active": detail.get("active"),
                        "released_date": released,
                        "requires_canonical_job_resolution": not bool(
                            detail.get("postingUrl")
                            or item.get("postingUrl")
                            or detail.get("jobAdUrl")
                            or item.get("jobAdUrl")
                        ),
                    },
                )
            )
        return [j for j in result if j.source_job_id and j.title and j.job_url]
