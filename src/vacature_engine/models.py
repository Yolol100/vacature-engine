from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .core import canonical_url, vacancy_id


@dataclass(slots=True)
class JobRecord:
    source: str
    source_job_id: str
    title: str
    employer: str
    job_url: str
    apply_url: str | None = None
    location: str | None = None
    is_remote: bool | None = None
    employment_type: str | None = None
    department: str | None = None
    team: str | None = None
    description: str | None = None
    posted_at: str | None = None
    salary_summary: str | None = None
    fetched_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def canonical_url(self) -> str:
        return canonical_url(self.job_url)

    @property
    def vacancy_id(self) -> str:
        return vacancy_id(self.employer, self.title, self.job_url)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["canonical_url"] = self.canonical_url
        data["vacancy_id"] = self.vacancy_id
        return data
