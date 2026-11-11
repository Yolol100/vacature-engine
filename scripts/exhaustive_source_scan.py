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

    The Google provider is handled separately by its free-quota gate.
    Results include only source IDs, safe outcome codes and attempt times.
    """
    if type(max_workers) is not int or not 1 <= max_workers <= 8:
        raise ValueError("Invalid bounded source concurrency")
    missing = [
        row for row in active_rows
        if str(row.get("status", "")).lower() == "active"
        and row.get("source_id") not in covered_source_ids
        and row.get("source_id") != "google-jobs"
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
