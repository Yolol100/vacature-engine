"""Read-only bridge to existing public Personio/Workable ingestion adapters.

Never creates ingestion SQLite state, Google writes, alerts or applications.
Only bounded public, employer-specific ATS data is returned to the Node reviewer.
"""
from __future__ import annotations

import json
import re
import sys

from .adapters.personio import PersonioAdapter
from .adapters.workable import WorkableAdapter
from .http import FetchError, HttpClient
from .models import SourceSpec

_SAFE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,79}$")
_JOB = re.compile(r"^[A-Za-z0-9_-]{1,120}$")
_PROVIDERS = {"personio": PersonioAdapter, "workable": WorkableAdapter}


def read_public(provider: str, account: str, employer: str, client=None) -> list[dict]:
    if provider not in _PROVIDERS or not _SAFE.fullmatch(account) or not employer or len(employer) > 120:
        raise ValueError("Invalid public ATS source")
    spec = SourceSpec(
        source_id=provider, source_type="ats", adapter=provider, account=account,
        employer=employer, listing_language="en", max_jobs=1000,
        options={"language": "en"},
    )
    adapter = _PROVIDERS[provider]()
    reader = client or HttpClient(timeout_seconds=10, retries=0, max_response_bytes=6_000_000)
    records = adapter.fetch(reader, spec)
    if len(records) > 1000:
        raise ValueError("Source exceeds safe job limit")
    jobs = []
    for record in records:
        normalized = adapter.normalize_record(record, spec, "")
        raw_id = record.get("shortcode") if provider == "workable" else record.get("id")
        job_id = str(raw_id or "").strip()
        if not normalized or not _JOB.fullmatch(job_id):
            raise ValueError("Invalid public ATS job")
        title = normalized.get("title") or ""
        url = normalized.get("canonical_url") or ""
        if not title or not url or len(title) > 240:
            raise ValueError("Invalid public ATS job data")
        jobs.append({
            "identity": f"{provider}:{account}:{job_id}",
            "source_id": provider, "source_account": account,
            "source_job_id": job_id, "employer": employer, "title": title,
            "url": url, "source_url": url,
            "location": normalized.get("location") or "",
            "remote": "remote" if normalized.get("remote") is True else
                (normalized.get("workplace_type") or ""),
        })
    return jobs


def main() -> int:
    try:
        if len(sys.argv) != 4:
            raise ValueError("Expected provider, account and employer")
        jobs = read_public(*sys.argv[1:])
        print(json.dumps({"jobs": jobs}, ensure_ascii=False))
        return 0
    except FetchError as error:
        # Do not print arbitrary provider URLs, bodies, credentials or request headers.
        print(f"public_ats_http_{error.status}" if error.status else "public_ats_fetch_error", file=sys.stderr)
    except Exception:
        print("public_ats_contract_error", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
