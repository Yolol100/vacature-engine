"""Optional, hard-bounded Google discovery via an existing FREE SerpApi account.

Search hits are unverified discovery observations. No inferred posting dates,
NL eligibility or employer identity; the caller verifies the canonical job page.
"""
from __future__ import annotations

import hashlib
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .base import Adapter, source_job_id
from ..http import FetchError
from ..models import SourceSpec
from ..normalize import clean_text, normalize_canonical_url
from ..ats_resolver import resolve_ats_url

_ACCOUNT_URL = "https://serpapi.com/account.json"
_SEARCH_URL = "https://serpapi.com/search.json"
_DEFAULT_QUERIES = (
    'site:jobs.ashbyhq.com ("WordPress" OR "WooCommerce") remote',
    'site:job-boards.greenhouse.io ("WordPress" OR "automation") remote',
    'site:jobs.lever.co ("WordPress" OR "web developer") remote',
    '"AI workflow automation" (remote OR worldwide)',
)


def _get_json(url: str, *, timeout: float) -> dict:
    """Keep sensitive URL/query/API-key completely out of all exceptions."""
    import json
    try:
        with urlopen(Request(url, headers={"Accept": "application/json", "User-Agent": "VacatureDiscovery/1.0"}), timeout=timeout) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise FetchError("response_too_large", "Search provider response too large")
            obj = json.loads(raw.decode("utf-8"))
            if not isinstance(obj, dict):
                raise ValueError("not an object")
            return obj
    except HTTPError as exc:
        raise FetchError("provider_http_error", f"Search provider HTTP {exc.code}", status=exc.code) from None
    except (URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
        raise FetchError("provider_unavailable", f"Search provider returned invalid/unavailable data ({type(exc).__name__})") from None


class SerpApiGoogleAdapter(Adapter):
    name = "serpapi_google"

    def fetch(self, client, spec: SourceSpec) -> list[dict]:
        if spec.source_id != "google-jobs" or spec.source_type != "discovery":
            raise ValueError("Use the active google-jobs discovery source; never create a second source")
        if spec.endpoint:
            raise ValueError("Custom provider endpoints are not accepted")
        key = os.environ.get("SERPAPI_API_KEY", "").strip()
        if not key:
            raise FetchError("not_configured", "Free Google discovery disabled: SERPAPI_API_KEY is absent")
        options = spec.options or {}
        queries = options.get("queries", list(_DEFAULT_QUERIES))
        if not isinstance(queries, list) or not queries or len(queries) > 20 or any(not isinstance(q, str) or not 3 <= len(q.strip()) <= 300 for q in queries):
            raise ValueError("queries must be 1-20 strings of 3-300 chars")
        max_pages = options.get("max_pages", 3)
        max_requests = options.get("max_requests_per_run", 12)
        reserve = options.get("free_quota_reserve", 10)
        if any(type(v) is not int for v in (max_pages, max_requests, reserve)) or not 1 <= max_pages <= 10 or not 1 <= max_requests <= 50 or not 0 <= reserve <= 100:
            raise ValueError("Invalid page/request/reserve limits")
        timeout = min(max(spec.timeout_seconds, 1), 25)
        account = _get_json(_ACCOUNT_URL + "?" + urlencode({"api_key": key}), timeout=timeout)
        name = str(account.get("plan_name", "")).strip().casefold()
        remaining = account.get("total_searches_left")
        if "free" not in name or type(remaining) is not int or remaining < max_requests + reserve:
            raise FetchError("free_quota_blocked", "Search disabled: confirmed FREE plan and sufficient remaining quota required")
        results = []
        requests = 0
        # At most one bounded crawl. Partial snapshots must NEVER close jobs.
        for query in queries:
            for page in range(max_pages):
                if requests >= max_requests or len(results) >= spec.max_jobs:
                    return results
                params = {"engine": "google", "q": query, "start": page * 10,
                          "hl": "en", "gl": "nl", "num": "10",
                          "tbs": "qdr:w", "api_key": key}
                payload = _get_json(_SEARCH_URL + "?" + urlencode(params), timeout=timeout)
                requests += 1
                if "error" in payload:
                    raise FetchError("provider_error", "Search provider reported an error; no further requests made")
                organic = payload.get("organic_results")
                if not isinstance(organic, list):
                    raise FetchError("malformed_result", "Search provider missing organic_results")
                for item in organic:
                    if not isinstance(item, dict):
                        continue
                    url = normalize_canonical_url(item.get("link"))
                    title = clean_text(item.get("title"), max_chars=400)
                    if url and url.startswith("https://") and title:
                        results.append({"url": url, "title": title, "snippet": clean_text(item.get("snippet"), max_chars=2000),
                                        "query": query, "page": page + 1})
                    if len(results) >= spec.max_jobs:
                        break
                if not organic:
                    break
        return results

    def normalize_record(self, record: dict, spec: SourceSpec, now: str) -> dict | None:
        url = normalize_canonical_url(record.get("url"))
        title = clean_text(record.get("title"), max_chars=400)
        if not url or not url.startswith("https://") or not title:
            return None
        hint = resolve_ats_url(url)
        return {
            "source_id": spec.source_id, "source_type": spec.source_type,
            "source_job_id": source_job_id(spec, hashlib.sha256(url.encode("utf-8")).hexdigest()),
            "source_instance": spec.instance_id,
            "source_url": "https://www.google.com/search",
            "canonical_url": url, "url": url,
            "employer": None, "title": title, "location": None,
            "description": clean_text(record.get("snippet"), max_chars=2000),
            "published_at": None, "updated_at": None, "valid_through": None,
            "employment_type": None, "salary": None, "listing_language": None,
            "apply_url": None, "remote": None, "workplace_type": None,
            "source_metadata": {"provider": "serpapi_google", "discovery_only": True,
                                "canonical_verification_required": True, "ats_hint": hint,
                                "query": clean_text(record.get("query"), max_chars=300),
                                "result_page": record.get("page"), "observation_time": now},
        }
