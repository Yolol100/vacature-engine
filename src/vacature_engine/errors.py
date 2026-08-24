from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FailureCategory(StrEnum):
    BLOCKED = "blocked/login-required"
    CAPTCHA = "CAPTCHA"
    ACCESS_RESTRICTION = "robots/access restriction"
    PAYWALL = "paywall"
    TRANSIENT = "timeout/transient network"
    MALFORMED = "malformed result"
    PARSING_CHANGE = "parsing/structure change"
    NOT_FOUND = "not found"
    UNEXPECTED_REDIRECT = "unexpected redirect"
    OTHER = "other technical failure"


@dataclass(slots=True)
class VacancyEngineError(RuntimeError):
    message: str
    category: FailureCategory = FailureCategory.OTHER
    status_code: int | None = None
    retryable: bool = False

    def __str__(self) -> str:
        return self.message
