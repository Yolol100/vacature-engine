__version__ = "3.6.0"

from .adapters import AdapterRegistry
from .core import canonical_url, content_hash, norm, vacancy_id
from .models import JobRecord
from .pipeline import (
    BatchResult,
    SourceSpec,
    deduplicate,
    fetch_many,
    fetch_source,
    filter_recency,
    posted_age_days,
)
from .policy import LOGIC_VERSION, application_guard, choose_application_language, hard_gate, score
from .structured import extract_jobposting_jsonld, jobposting_facts

__all__ = [
    "AdapterRegistry",
    "BatchResult",
    "JobRecord",
    "LOGIC_VERSION",
    "SourceSpec",
    "application_guard",
    "canonical_url",
    "choose_application_language",
    "content_hash",
    "deduplicate",
    "fetch_many",
    "fetch_source",
    "filter_recency",
    "hard_gate",
    "norm",
    "posted_age_days",
    "score",
    "extract_jobposting_jsonld",
    "jobposting_facts",
    "vacancy_id",
]
