from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

OBSERVATION_CONTRACT_VERSION = "1.1"


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    source_type: str
    adapter: str
    account: str
    employer: str | None = None
    endpoint: str | None = None
    listing_language: str | None = None
    max_jobs: int = 20_000
    timeout_seconds: float = 20.0
    retries: int = 2
    max_response_bytes: int = 50 * 1024 * 1024
    missing_close_threshold: int = 2
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def instance_id(self) -> str:
        return f"{self.source_id}:{self.account}"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceSpec":
        allowed = {
            "source_id", "source_type", "adapter", "account", "employer", "endpoint",
            "listing_language", "max_jobs", "timeout_seconds", "retries",
            "max_response_bytes", "missing_close_threshold", "options",
        }
        clean = {key: value for key, value in data.items() if key in allowed}
        return cls(**clean)
