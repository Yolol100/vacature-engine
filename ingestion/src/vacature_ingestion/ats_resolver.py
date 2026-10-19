"""Recognize public ATS tenants from career URLs; never activate a source automatically."""
from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

_PATH_HOSTS = {
    "jobs.ashbyhq.com": "ashby",
    "jobs.lever.co": "lever",
    "jobs.eu.lever.co": "lever",
    "boards.greenhouse.io": "greenhouse",
    "job-boards.greenhouse.io": "greenhouse",
    "boards.eu.greenhouse.io": "greenhouse",
    "job-boards.eu.greenhouse.io": "greenhouse",
    "apply.workable.com": "workable",
    "jobs.smartrecruiters.com": "smartrecruiters",
    "careers.smartrecruiters.com": "smartrecruiters",
    "ats.rippling.com": "rippling",
}
_SUBDOMAIN_HOSTS = {
    ".recruitee.com": "recruitee",
    ".breezy.hr": "breezy",
    ".jobs.personio.com": "personio",
    ".jobs.personio.de": "personio",
    ".teamtailor.com": "teamtailor",
    ".bamboohr.com": "bamboohr",
}
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._%-]{0,119}$")


def resolve_ats_url(url: str) -> dict[str, str] | None:
    """Return a provider hint. A matched hostname is NOT employer verification."""
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.port not in (None, 443):
            return None
        if host in _PATH_HOSTS:
            parts = [unquote(part) for part in parsed.path.split("/") if part]
            if host == "apply.workable.com" and len(parts) >= 2 and parts[0] == "j":
                return None  # Job ID does not identify an employer tenant.
            if not parts or not _TOKEN.fullmatch(parts[0]) or parts[0] in (".", ".."):
                return None
            return {"provider": _PATH_HOSTS[host], "account": parts[0], "careers_url": f"https://{host}/{parts[0]}"}
        for suffix, provider in _SUBDOMAIN_HOSTS.items():
            if host.endswith(suffix):
                token = host[:-len(suffix)]
                if token and "." not in token and _TOKEN.fullmatch(token):
                    return {"provider": provider, "account": token, "careers_url": f"https://{host}"}
    except (ValueError, UnicodeError):
        return None
    return None
