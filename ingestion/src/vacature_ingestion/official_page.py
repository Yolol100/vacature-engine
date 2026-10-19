"""Bounded, read-only official ATS page evidence; never a new discovery source.

Only static recognized ATS tenant hosts can be requested. Redirects are rejected
(including cross-host redirects) and the response is capped. No login,
submission, browser execution, tokens or candidate data are sent.
"""
from __future__ import annotations

import json
from datetime import date
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from typing import Any

from vacature_engine.observations import is_role_specific_vacancy_url
from vacature_engine.structured import jobposting_signals

_STATIC_ATS_HOSTS = {
    "ashby": {"jobs.ashbyhq.com"},
    "greenhouse": {"boards.greenhouse.io", "job-boards.greenhouse.io",
                   "boards.eu.greenhouse.io", "job-boards.eu.greenhouse.io"},
    "lever": {"jobs.lever.co", "jobs.eu.lever.co"},
    "workable": {"apply.workable.com"},
}
_LIMIT = 256 * 1024


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class _Markup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.language: str | None = None
        self._json_active = False
        self._scripts: list[str] = []
        self._buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        info = dict(attrs)
        if tag == "html" and self.language is None:
            language = info.get("lang")
            if isinstance(language, str):
                norm = language.strip().casefold().split("-")[0]
                self.language = norm if norm in {"en", "nl", "de", "fr", "es", "pt"} else None
        if tag == "script" and info.get("type", "").casefold() == "application/ld+json":
            self._json_active = True
            self._buffer = []

    def handle_data(self, data):
        if self._json_active and sum(len(x) for x in self._buffer) < 100_000:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._json_active:
            self._json_active = False
            snippet = "".join(self._buffer)
            if len(snippet) <= 100_000 and len(self._scripts) < 12:
                self._scripts.append(snippet)
            self._buffer = []


def _jobposting_nodes(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _jobposting_nodes(item)
    elif isinstance(value, dict):
        type_value = value.get("@type")
        if (type_value == "JobPosting" or
                isinstance(type_value, list) and "JobPosting" in type_value):
            yield value
        graph = value.get("@graph")
        if isinstance(graph, list):
            yield from _jobposting_nodes(graph)


def _matches_identity(signals: dict[str, Any], title: str, employer: str) -> bool:
    posted_title = signals.get("title")
    org = signals.get("hiring_organization")
    if not isinstance(posted_title, str) or not isinstance(org, str):
        return False
    normal = lambda s: " ".join(s.casefold().replace("-", " ").split())
    a, b = normal(posted_title), normal(title)
    if a != b:
        return False
    company, expected = normal(org), normal(employer)
    return company == expected


def extract_ats_page_signals(html: str, *, title: str, employer: str, today: date) -> dict[str, Any]:
    """Read only matching first-party JSON-LD; schema alone is not a hiring proof."""
    parser = _Markup()
    parser.feed(html[:_LIMIT])
    matching: list[dict[str, Any]] = []
    for script in parser._scripts:
        try:
            obj = json.loads(script)
        except (ValueError, TypeError):
            continue
        for node in _jobposting_nodes(obj):
            signals = jobposting_signals(node, today=today)
            if signals["is_job_posting"] and _matches_identity(signals, title, employer):
                matching.append(signals)
    if len(matching) != 1:
        # Multiple conflicting JobPosting records cannot be picked arbitrarily.
        return {"page_language": parser.language, "structured": None,
                "status": "no_unique_matching_first_party_jobposting"}
    return {"page_language": parser.language, "structured": matching[0], "status": "matching_first_party_jobposting"}


def _trusted_tenant_url(url: Any, *, provider: str, account: str) -> bool:
    """An arbitrary Google/board URL cannot become official by hostname alone."""
    if not isinstance(url, str) or not is_role_specific_vacancy_url(url):
        return False
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        host = (parsed.hostname or "").casefold()
        parts = [unquote(p).casefold() for p in parsed.path.split("/") if p]
        tenant = account.casefold()
        if provider == "personio":
            return host in {tenant + ".jobs.personio.com", tenant + ".jobs.personio.de"} and len(parts) >= 2
        if host not in _STATIC_ATS_HOSTS.get(provider, set()):
            return False
        return bool(parts) and parts[0] == tenant and len(parts) >= 2
    except (ValueError, UnicodeError):
        return False


def verified_source_account(row: dict[str, Any], *, active_ids: set[str]) -> tuple[str, str] | None:
    provider = row.get("source_id")
    instance = row.get("source_instance")
    metadata = row.get("source_metadata")
    if (row.get("source_type") != "ats" or provider not in active_ids
            or not isinstance(instance, str)
            or not isinstance(metadata, dict) or metadata.get("provider") != provider):
        return None
    prefix = provider + ":"
    if not instance.startswith(prefix) or not instance[len(prefix):]:
        return None
    account = instance[len(prefix):]
    if not _trusted_tenant_url(row.get("canonical_url"), provider=provider, account=account):
        return None
    return provider, account


def _fetch_html(url: str) -> tuple[int, str | None]:
    """No redirect following, no cookies or secrets; HTTPS trusted tenant only."""
    opener = build_opener(_NoRedirect())
    request = Request(url, headers={
        "User-Agent": "Webactueel-Vacature-Verification/0.1",
        "Accept": "text/html,application/xhtml+xml",
    }, method="GET")
    try:
        with opener.open(request, timeout=8) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                return int(response.status), None
            data = response.read(_LIMIT + 1)
            if len(data) > _LIMIT:
                return int(response.status), None
            return int(response.status), data.decode("utf-8", errors="replace")
    except HTTPError as exc:
        return int(exc.code), None
    except (URLError, TimeoutError, ValueError, OSError):
        return 0, None


def fetch_official_page_evidence(row: dict[str, Any], *,
                                 active_ids: set[str], today: date) -> dict[str, Any]:
    """Fetch the exact listed job + apply route only after a trusted ATS gate."""
    source = verified_source_account(row, active_ids=active_ids)
    report: dict[str, Any] = {"status": "unverified", "job_http_status": None,
                              "apply_http_status": None, "page_language": None,
                              "application_language": None, "structured": None}
    if source is None:
        return report
    provider, account = source
    url = row["canonical_url"]
    job_status, body = _fetch_html(url)
    report["job_http_status"] = job_status
    if job_status in (404, 410):
        report["status"] = "closed_at_exact_ats_route"
        return report
    if job_status != 200 or not body:
        return report
    parsed = extract_ats_page_signals(body, title=str(row.get("title") or ""),
                                      employer=str(row.get("employer") or ""), today=today)
    report["page_language"] = parsed["page_language"]
    report["structured"] = parsed["structured"]
    report["status"] = parsed["status"]

    apply = row.get("apply_url") or url
    if not _trusted_tenant_url(apply, provider=provider, account=account):
        report["status"] = "application_route_unverified"
        return report
    if apply == url:
        # A job description page is not itself proof of an application form.
        return report
    apply_status, apply_body = _fetch_html(apply)
    report["apply_http_status"] = apply_status
    if apply_status == 200 and apply_body:
        parser = _Markup()
        parser.feed(apply_body)
        report["application_language"] = parser.language
    return report
