"""Optional, hard-bounded Google discovery via an existing FREE SerpApi account.

Search hits are unverified discovery observations. No inferred posting dates,
NL eligibility or employer identity; the caller verifies the canonical job page.
"""
from __future__ import annotations

import hashlib
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .base import Adapter, source_job_id
from ..models import SourceSpec
from ..normalize import clean_text, normalize_canonical_url
from ..ats_resolver import resolve_ats_url
from ..http import FetchError


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


def _is_safe_free_account(account: dict, planned_requests: int, reserve: int) -> bool:
    """Use the official account fields; missing/ambiguous billing data must block."""
    if str(account.get("account_status", "")).casefold() != "active":
        return False
    if str(account.get("plan_id", "")).casefold() != "free":
        return False
    if str(account.get("plan_name", "")).strip().casefold() not in {"free", "free plan"}:
        return False
    price = account.get("plan_monthly_price")
    quota = account.get("searches_per_month")
    extra = account.get("extra_credits")
    left = account.get("plan_searches_left")
    total_left = account.get("total_searches_left")
    if type(price) not in (int, float) or price != 0:
        return False
    if type(quota) is not int or not 1 <= quota <= 250:
        return False
    if type(extra) is not int or extra != 0:
        return False
    if type(left) is not int or type(total_left) is not int or min(left, total_left) < planned_requests + reserve:
        return False
    hourly_limit = account.get("account_rate_limit_per_hour")
    hourly_used = account.get("this_hour_searches")
    if hourly_limit is not None and hourly_used is not None:
        if type(hourly_limit) is not int or type(hourly_used) is not int:
            return False
        if hourly_limit - hourly_used < planned_requests:
            return False
    return True


def _safe_candidate_url(value: object) -> str | None:
    """Reject credentials, local hosts and malformed URL ports before normalization."""
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value.strip())
        host = (parts.hostname or "").casefold()
        if parts.scheme != "https" or not host or parts.username or parts.password:
            return None
        if host in {"localhost", "127.0.0.1", "0.0.0.0", "[::1]"} or host.endswith((".local", ".test")):
            return None
        if parts.port not in (None, 443):
            return None
    except ValueError:
        return None
    return normalize_canonical_url(value)


class SerpApiGoogleAdapter(Adapter):
    complete_snapshot = False
    name = "serpapi_google"

    def fetch(self, client, spec: SourceSpec) -> list[dict]:
        if spec.source_id != "google-jobs" or spec.source_type != "discovery":
            raise ValueError("Use the active google-jobs discovery source; never create a second source")
        if spec.endpoint:
            raise ValueError("Custom provider endpoints are not accepted")
        key = os.environ.get("SERPAPI_API_KEY", "").strip()
        if not key:
            raise FetchError("not_configured", "Free Google discovery disabled: SERPAPI_API_KEY is absent")
        options = spec.options
        if not isinstance(options, dict):
            raise ValueError("Search options must be a mapping")
        queries = options.get("queries", list(_DEFAULT_QUERIES))
        if not isinstance(queries, list) or not 1 <= len(queries) <= 20 or any(
            not isinstance(q, str) or not 3 <= len(q.strip()) <= 300 for q in queries
        ):
            raise ValueError("queries must be 1-20 strings of 3-300 chars")
        # Do not spend quota searching an identical query twice.
        queries = list(dict.fromkeys(q.strip() for q in queries))
        max_pages = options.get("max_pages", 3)
        max_requests = options.get("max_requests_per_run", 12)
        reserve = options.get("free_quota_reserve", 10)
        time_range = options.get("time_range", "week")
        if (
            any(type(v) is not int for v in (max_pages, max_requests, reserve))
            or not 1 <= max_pages <= 10
            or not 1 <= max_requests <= 50
            or not 0 <= reserve <= 100
            or time_range not in {"day", "week"}
        ):
            raise ValueError("Invalid page, request, time-range or reserve limits")
        planned = min(max_requests, len(queries) * max_pages)
        timeout = min(max(spec.timeout_seconds, 1), 25)
        account = _get_json(_ACCOUNT_URL + "?" + urlencode({"api_key": key}), timeout=timeout)
        if not _is_safe_free_account(account, planned, reserve):
            raise FetchError(
                "free_quota_blocked",
                "Search disabled: a verified active free plan and sufficient free quota are required",
            )

        # Round-robin pages so a single query never consumes the whole quota
        # while other configured terms receive no discovery coverage.
        results: list[dict] = []
        seen: set[str] = set()
        exhausted: set[str] = set()
        requests = 0
        for page in range(max_pages):
            for query in queries:
                if query in exhausted:
                    continue
                if requests >= max_requests or len(results) >= spec.max_jobs:
                    return results
                params = {
                    "engine": "google",
                    "q": query,
                    "start": page * 10,
                    "hl": "en",
                    "num": "10",
                    "tbs": "qdr:d" if time_range == "day" else "qdr:w",
                    "api_key": key,
                }
                payload = _get_json(_SEARCH_URL + "?" + urlencode(params), timeout=timeout)
                requests += 1
                if "error" in payload:
                    raise FetchError("provider_error", "Search provider returned an error; stopping")
                organic = payload.get("organic_results")
                if not isinstance(organic, list):
                    raise FetchError("malformed_result", "Search provider missing organic_results")
                added = 0
                for item in organic:
                    if not isinstance(item, dict):
                        continue
                    url = _safe_candidate_url(item.get("link"))
                    title = clean_text(item.get("title"), max_chars=400)
                    if url and title and url not in seen:
                        seen.add(url)
                        results.append({
                            "url": url,
                            "title": title,
                            "snippet": clean_text(item.get("snippet"), max_chars=2000),
                            "query": query,
                            "page": page + 1,
                        })
                        added += 1
                        if len(results) >= spec.max_jobs:
                            return results
                if not organic or not added:
                    # Empty or repeating result pages are not evidence of a full snapshot.
                    exhausted.add(query)
            if len(exhausted) == len(queries):
                break
        return results

    def normalize_record(self, record: dict, spec: SourceSpec, now: str) -> dict | None:
        url = _safe_candidate_url(record.get("url"))
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
