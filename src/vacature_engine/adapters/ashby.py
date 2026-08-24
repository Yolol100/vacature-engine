from __future__ import annotations

from urllib.parse import quote

from ..models import JobRecord
from .base import AdapterRegistry, BaseAdapter


def _salary_summary(comp: object) -> str | None:
    if not isinstance(comp, dict):
        return None
    summary = (
        comp.get("scrapeableCompensationSalarySummary")
        or comp.get("compensationTierSummary")
        or comp.get("summary")
    )
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
            workplace = str(item.get("workplaceType") or "").strip().lower()
            if workplace == "remote":
                is_remote: bool | None = True
            elif workplace in {"hybrid", "onsite", "on-site"}:
                is_remote = False
            else:
                is_remote = item.get("isRemote") if isinstance(item.get("isRemote"), bool) else None
            last_published = str(item.get("publishedAt") or "").strip() or None
            result.append(
                JobRecord(
                    source=self.source,
                    source_job_id=str(
                        item.get("id") or item.get("jobPostingId") or item.get("jobUrl") or ""
                    ),
                    title=str(item.get("title", "")).strip(),
                    employer=self.slug,
                    job_url=str(item.get("jobUrl", "")).strip(),
                    apply_url=str(item.get("applyUrl") or "").strip() or None,
                    location=str(item.get("location") or "").strip() or None,
                    is_remote=is_remote,
                    employment_type=str(item.get("employmentType") or "").strip() or None,
                    department=str(item.get("department") or "").strip() or None,
                    team=str(item.get("team") or "").strip() or None,
                    description=str(item.get("descriptionPlain") or item.get("description") or "").strip()
                    or None,
                    posted_at=None,
                    source_date=last_published,
                    source_date_semantics="last_published" if last_published else None,
                    salary_summary=_salary_summary(item.get("compensation")),
                    raw={
                        "address": item.get("address"),
                        "secondary_locations": item.get("secondaryLocations"),
                        "compensation": item.get("compensation"),
                        "last_published_at": item.get("publishedAt"),
                    },
                )
            )
        return [j for j in result if j.source_job_id and j.title and j.job_url]
