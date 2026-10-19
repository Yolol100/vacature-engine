"""Read-only bridge to existing public Personio/Workable ingestion adapters.

Never creates ingestion SQLite state, Google writes, alerts or applications.
Only bounded public, employer-specific ATS data is returned to the Node reviewer.
"""
from __future__ import annotations

import json
import re
import sys
from urllib.parse import urlsplit

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
        if provider == "workable":
            # Public tenant feed proves job ownership; shortlinks omit tenant.
            parts = urlsplit(url)
            allowed = {f"/j/{job_id}", f"/{account}/j/{job_id}"}
            if (parts.scheme != "https" or parts.netloc.lower() != "apply.workable.com"
                    or parts.path.rstrip("/") not in allowed or parts.username or parts.password):
                raise ValueError("Invalid public ATS job data")
            url = f"https://apply.workable.com/{account}/j/{job_id}"
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


# The existing deploy manifest is the sole technical source inventory.
# This extra read-only path never starts IngestionRunner or opens SQLite.
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from .adapters import ADAPTERS

_DISCOVERY_ADAPTERS = {
    "remotive": ("remotive", "discovery_api", None),
    "jobicy-api": ("jobicy", "discovery_api", None),
    "himalayas": ("himalayas", "discovery_api", None),
    "we-work-remotely": ("weworkremotely", "job_board",
                          "https://weworkremotely.com/categories/remote-programming-jobs.rss"),
    "remote-ok": ("remoteok", "job_board", "https://remoteok.com/api"),
    "remote-landers-api": ("publicfeeds", "discovery_api", None),
    "remotejobs-org": ("publicfeeds", "discovery_api", None),
    "arbeitnow-api": ("publicfeeds", "discovery_api", None),
}
_DEPLOY_MANIFEST = Path(__file__).resolve().parents[2] / "source-specs.deploy.json"


def read_discovery(provider: str, client=None, *, manifest_path=None) -> list[dict]:
    """Bounded publicly documented API/RSS discovery; results are NOT verified jobs."""
    expected = _DISCOVERY_ADAPTERS.get(provider)
    if not expected:
        raise ValueError("Unsupported discovery source")
    path = manifest_path or _DEPLOY_MANIFEST
    specs = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(specs, list):
        raise ValueError("Invalid deployment source manifest")
    matches = [row for row in specs if isinstance(row, dict) and row.get("source_id") == provider]
    if len(matches) != 1:
        raise ValueError("Missing or duplicate discovery source")
    raw = matches[0]
    if (raw.get("adapter"), raw.get("source_type"), raw.get("endpoint")) != expected:
        raise ValueError("Unexpected discovery source contract")
    if raw.get("account") not in {"global", "programming"} or not isinstance(raw.get("max_jobs"), int):
        raise ValueError("Invalid discovery source limits")
    if raw["max_jobs"] < 1 or raw["max_jobs"] > 20000:
        raise ValueError("Invalid discovery source limits")
    spec = replace(SourceSpec.from_dict(raw), max_jobs=min(raw["max_jobs"], 120),
                   retries=0, timeout_seconds=8, max_response_bytes=12_000_000)
    fetcher = client or HttpClient(timeout_seconds=8, retries=0, max_response_bytes=12_000_000)
    adapter = ADAPTERS[spec.adapter]
    records = adapter.fetch(fetcher, spec)
    if not isinstance(records, list) or len(records) > spec.max_jobs:
        raise ValueError("Invalid bounded discovery response")
    out = []
    quarantined = 0
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Invalid discovery record")
        try:
            row = adapter.normalize_record(record, spec, "")
        except ValueError as error:
            # Only Arbeitnow's known third-party URL contract may be isolated.
            # Never accept that URL, never print it, and never claim a full pass.
            if adapter.can_quarantine_record_error(spec, error):
                quarantined += 1
                continue
            raise
        if row is None:
            continue
        title = str(row.get("title") or "").strip()
        employer = str(row.get("employer") or "").strip()
        address = str(row.get("canonical_url") or "").strip()
        parts = urlsplit(address)
        if (not title or len(title) > 240 or len(address) > 2000 or
            parts.scheme != "https" or not parts.netloc or parts.username or parts.password):
            raise ValueError("Invalid public discovery role")
        base_id = str(row.get("source_job_id") or address)
        key = sha256(base_id.encode("utf-8")).hexdigest()[:24]
        out.append({
            "identity": f"{provider}:{spec.account}:{key}",
            "source_id": provider, "source_account": spec.account,
            "source_job_id": key, "employer": employer[:160], "title": title,
            "url": address, "source_url": str(row.get("source_url") or "")[:240],
            "location": str(row.get("location") or "")[:160],
            "remote": ("remote" if row.get("remote") is True else
                       str(row.get("workplace_type") or row.get("remote") or "")[:80]),
        })
    return {"jobs": out, "quarantined": quarantined}


def main() -> int:
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--discovery":
            result = read_discovery(sys.argv[2])
            jobs = result["jobs"]
        elif len(sys.argv) == 4:
            jobs = read_public(*sys.argv[1:])
        else:
            raise ValueError("Expected bounded public source arguments")
        print(json.dumps({"jobs": jobs, "quarantined": result["quarantined"] if len(sys.argv) == 3 else 0}, ensure_ascii=False))
        return 0
    except FetchError as error:
        # One fixed category only; never emit response bodies, URLs or credentials.
        category = error.category if error.category in {
            "timeout_or_network", "malformed_result", "response_too_large",
            "rate_limited", "upstream_transient", "blocked_or_auth_required",
            "other_technical_failure", "http_error",
        } else "other_technical_failure"
        print(f"public_ats_http_{error.status}" if error.status else
              f"public_ats_fetch_{category}", file=sys.stderr)
    except ValueError as error:
        # Provider-controlled exception messages are never printed.
        category = {
            "Invalid Arbeitnow response": "schema",
            "Unexpected public feed job URL": "job_url",
            "Unexpected public feed job URL: malformed": "job_url_malformed",
            "Unexpected public feed job URL: uk_apex": "job_url_uk_apex",
            "Unexpected public feed job URL: untrusted_host": "job_url_untrusted_host",
            "Invalid public discovery role": "normalized_role",
        }.get(str(error), "other")
        print(f"public_ats_contract_{category}", file=sys.stderr)
    except Exception:
        print("public_ats_internal_error", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
