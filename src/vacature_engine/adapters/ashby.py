from __future__ import annotations

from urllib.parse import quote

from .base import AdapterRegistry, BaseAdapter
from ..models import JobRecord


def _salary_summary(comp: object) -> str | None:
    if not isinstance(comp, dict):
        return None
    summary = comp.get("summary") or comp.get("scrapeableCompensationSalarySummary")
    return str(summary).strip() if summary else None


@AdapterRegistry.register
class AshbyAdapter(BaseAdapter):
    source = "ashby"

    def fetch(self) -> list[JobRecord]:
        url = (
            "https://api.ashbyhq.com/posting-api/job-board/"
            f"{quote(self.slug, safe='')}?includeCompensation=true"
        )
        payload = self.client.get_json(url, allowed_hosts={"api.ashbyhq.com"})
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise ValueError("ashby payload missing jobs[]")
        result: list[JobRecord] = []
        for item in jobs:
            if not isinstance(item, dict) or item.get("isListed") is False:
                continue
            result.append(
                JobRecord(
                    source=self.source,
                    source_job_id=str(item.get("id") or item.get("jobPostingId") or item.get("jobUrl") or ""),
                    title=str(item.get("title", "")).strip(),
                    employer=self.slug,
                    job_url=str(item.get("jobUrl", "")).strip(),
                    apply_url=str(item.get("applyUrl") or "").strip() or None,
                    location=str(item.get("location") or "").strip() or None,
                    is_remote=item.get("isRemote") if isinstance(item.get("isRemote"), bool) else None,
                    employment_type=str(item.get("employmentType") or "").strip() or None,
                    department=str(item.get("department") or "").strip() or None,
                    team=str(item.get("team") or "").strip() or None,
                    description=str(item.get("descriptionPlain") or item.get("description") or "").strip() or None,
                    posted_at=str(item.get("publishedAt") or "").strip() or None,
                    salary_summary=_salary_summary(item.get("compensation")),
                    raw={
                        "address": item.get("address"),
                        "secondary_locations": item.get("secondaryLocations"),
                        "compensation": item.get("compensation"),
                    },
                )
            )
        return [j for j in result if j.source_job_id and j.title and j.job_url]
