"""Bounded, read-only website reachability checks for active Register sources.

These probes consult each registered public URL once; they do not extract or
verify vacancies. Failure is unknown/blocked, never evidence of zero jobs.
"""
from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _public_url(value: str) -> bool:
    try:
        parsed = urlsplit(str(value or "").strip())
        host = (parsed.hostname or "").rstrip(".").lower()
        if (parsed.scheme not in {"https", "http"} or not host or
                parsed.username or parsed.password or parsed.port not in (None, 80, 443)):
            return False
        if host in {"localhost", "localhost.localdomain"} or host.endswith(
                (".local", ".internal", ".localhost", ".test", ".invalid")):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        addresses = socket.getaddrinfo(host, 443 if parsed.scheme == "https" else 80)
        return bool(addresses) and all(
            ipaddress.ip_address(item[4][0]).is_global for item in addresses
        )
    except (ValueError, OSError, IndexError):
        return False


def probe_public_landing(url: str) -> tuple[bool, str | None]:
    """One public GET without redirect following, with small time/body budgets."""
    if not _public_url(url):
        return False, "unsafe_or_unresolvable_url"
    request = Request(
        url, headers={
            "User-Agent": "Webactueel-Vacature-SourceCheck/1.0",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.8,*/*;q=0.5",
        }, method="GET",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=6) as response:
            if not 200 <= response.status < 300:
                return False, "unexpected_http_status"
            response.read(8192)
        return True, None
    except HTTPError as exc:
        if exc.code in (401, 403):
            return False, "blocked_or_login_required"
        if exc.code == 429:
            return False, "rate_limited"
        if 300 <= exc.code < 400:
            return False, "redirect_requires_review"
        if 500 <= exc.code < 600:
            return False, "upstream_transient"
        return False, "http_error"
    except (URLError, TimeoutError, OSError):
        return False, "timeout_or_network"


def probe_unadapted_active_sources(
    active_rows: list[dict[str, str]], covered_source_ids: set[str], *,
    probe: Callable[[str], tuple[bool, str | None]] = probe_public_landing,
    max_workers: int = 6,
) -> list[dict[str, Any]]:
    """Probe active sources not covered by an ATS/feed adapter.

    The Google provider is queried here only if its separately gated API was not attempted.
    Results include only source IDs, safe outcome codes and attempt times.
    """
    if type(max_workers) is not int or not 1 <= max_workers <= 8:
        raise ValueError("Invalid bounded source concurrency")
    missing = [
        row for row in active_rows
        if str(row.get("status", "")).lower() == "active"
        and row.get("source_id") not in covered_source_ids
    ]
    seen: set[str] = set()
    for row in missing:
        source_id = row.get("source_id")
        if not source_id or source_id in seen:
            raise ValueError("Missing or duplicated active source ID")
        seen.add(source_id)

    def one(row: dict[str, str]) -> dict[str, Any]:
        source_id = row["source_id"]
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            success, failure_category = probe(row.get("base_url", ""))
            if type(success) is not bool:
                raise ValueError("Invalid source probe result")
        except Exception:
            success, failure_category = False, "probe_internal_failure"
        return {
            "source_instance": "web:" + source_id,
            "registry_source_ids": [source_id],
            "started_at": started_at,
            "success": success,
            "fetched": 0,
            "normalized": 0,
            "quarantine_count": 0,
            "complete_snapshot": False,
            "failure_category": failure_category if not success else None,
            "attempt_kind": "public_landing_probe_only",
        }

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(one, missing))


# Secondary route for sites without a deploy adapter. Unlike reachability-only
# probes, this collects public, job-specific anchor links for specialist review.
# No extracted link is EVER considered an authenticated or verified vacancy.
from html.parser import HTMLParser
import re
from urllib.parse import urljoin

from vacature_engine.observations import (
    is_role_specific_vacancy_url, normalize_canonical_url,
)

_ROLE_WORD = re.compile(r"\b(?:wordpress|woocommerce|gutenberg|elementor|acf)\b", re.I)
_JOB_WORD = re.compile(
    r"\b(?:developer|ontwikkelaar|engineer|specialist|support|designer|"
    r"consultant|webmaster|administrator|beheerder|technician)\b", re.I,
)
_MAX_HTML_BYTES = 256 * 1024
_MAX_JOB_LINKS = 25


class _PublicJobLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._title: list[str] = []
        self._inside_anchor = False
        self._hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._hidden_depth += 1
        if tag == "a" and self._hidden_depth == 0 and not self._inside_anchor:
            href = dict(attrs).get("href")
            self._href = href if isinstance(href, str) else None
            self._title = []
            self._inside_anchor = True

    def handle_data(self, data):
        if self._inside_anchor and self._hidden_depth == 0 and len(self._title) < 25:
            self._title.append(data[:300])

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self._hidden_depth = max(0, self._hidden_depth - 1)
        if tag == "a" and self._inside_anchor:
            if self._href and len(self.links) < 300:
                title = " ".join(" ".join(self._title).split())[:180]
                self.links.append((self._href, title))
            self._href = None
            self._title = []
            self._inside_anchor = False


def _safe_discovered_url(value: str) -> str | None:
    candidate = normalize_canonical_url(value)
    if not candidate or len(candidate) > 2000:
        return None
    try:
        parts = urlsplit(candidate)
        host = (parts.hostname or "").casefold()
        if (parts.scheme != "https" or not host or "." not in host
                or parts.username or parts.password or parts.port not in (None, 443)
                or host.endswith((".local", ".internal", ".localhost", ".test", ".invalid"))):
            return None
        try:
            ipaddress.ip_address(host)
            return None
        except ValueError:
            pass
    except ValueError:
        return None
    return candidate if is_role_specific_vacancy_url(candidate) else None


def public_job_links(html: str, source: dict[str, str]) -> list[dict[str, Any]]:
    """Extract bounded role links as UNVERIFIED discovery, no publication proof."""
    base_url = source.get("base_url", "")
    source_id = source.get("source_id", "")
    if not source_id or not base_url or not isinstance(html, str):
        return []
    parser = _PublicJobLinkParser()
    try:
        parser.feed(html[:_MAX_HTML_BYTES])
    except (ValueError, AssertionError):
        return []
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for raw_url, title in parser.links:
        if not (_ROLE_WORD.search(title) and _JOB_WORD.search(title)):
            continue
        if not raw_url or raw_url.startswith(("#", "javascript:", "mailto:", "data:")):
            continue
        url = _safe_discovered_url(urljoin(base_url, raw_url))
        if not url or url in seen:
            continue
        seen.add(url)
        row = {
            "source_id": source_id,
            "source_type": "discovery",
            "canonical_url": url,
            "url": url,
            "title": title,
            "employer": (
                source.get("source_name")
                if source.get("source_type") == "employer_direct" else None
            ),
            "source_metadata": {"public_html_job_link_unverified": True},
        }
        result.append(row)
        if len(result) >= _MAX_JOB_LINKS:
            break
    return result


def fetch_public_job_html(url: str) -> tuple[str | None, str | None]:
    """One bounded no-redirect public GET; never follow extracted job links."""
    if not _public_url(url):
        return None, "unsafe_or_unresolvable_url"
    request = Request(
        url,
        headers={"User-Agent": "Webactueel-Vacature-SourceCheck/1.0",
                 "Accept": "text/html,application/xhtml+xml"},
        method="GET",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=6) as response:
            kind = response.headers.get("Content-Type", "").lower()
            if "html" not in kind:
                return None, "not_html"
            content = response.read(_MAX_HTML_BYTES + 1)
            if len(content) > _MAX_HTML_BYTES:
                return None, "page_too_large_for_safe_extract"
            return content.decode("utf-8", errors="replace"), None
    except HTTPError as exc:
        if exc.code in (401, 403):
            return None, "blocked_or_login_required"
        if exc.code == 429:
            return None, "rate_limited"
        if 300 <= exc.code < 400:
            return None, "redirect_requires_review"
        return None, "http_error"
    except (URLError, TimeoutError, OSError):
        return None, "timeout_or_network"


def scan_unadapted_public_job_links(
    active_rows: list[dict[str, str]], covered_source_ids: set[str], *,
    fetch: Callable[[str], tuple[str | None, str | None]] = fetch_public_job_html,
    max_workers: int = 6,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read public landing pages and return (source attempts, unverified links).

    Errors never imply zero vacancies. The ledger contains no HTML or text.
    The discovered observations remain pending until official role verification.
    """
    if type(max_workers) is not int or not 1 <= max_workers <= 8:
        raise ValueError("Invalid bounded source concurrency")
    missing = [
        row for row in active_rows
        if str(row.get("status", "")).casefold() == "active"
        and row.get("source_id") not in covered_source_ids
    ]
    ids = [row.get("source_id") for row in missing]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("Missing or duplicated active source ID")

    def one(row: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        source_id = row["source_id"]
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            html, error = fetch(row.get("base_url", ""))
            jobs = public_job_links(html, row) if isinstance(html, str) else []
            success = isinstance(html, str)
            if html is None and not error:
                error = "fetch_unavailable"
        except Exception:
            jobs, success, error = [], False, "probe_internal_failure"
        audit = {
            "source_instance": "web:" + source_id,
            "registry_source_ids": [source_id],
            "started_at": started_at,
            "success": success,
            "fetched": len(jobs),
            "normalized": len(jobs),
            "quarantine_count": 0,
            "complete_snapshot": False,
            "failure_category": error if not success else None,
            "attempt_kind": "public_html_job_link_discovery" if success else "public_landing_probe_failed",
            "candidate_links_unverified": len(jobs),
        }
        return audit, jobs

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(one, missing))
    return ([audit for audit, _ in results],
            [job for _, observations in results for job in observations])

