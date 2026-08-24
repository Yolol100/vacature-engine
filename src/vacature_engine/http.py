from __future__ import annotations

import ipaddress
import json
import math
import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .errors import FailureCategory, VacancyEngineError

USER_AGENT = "vacature-engine/3.1 (+public vacancy verification; no access-control bypass)"
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
BLOCKED_STATUSES = {401, 403, 406}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".home", ".lan")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _retry_after_seconds(value: str | None, now: float) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value).timestamp()
        return max(0.0, when - now)
    except (TypeError, ValueError, OverflowError):
        return None


def _normalized_allowed_hosts(allowed_hosts: set[str] | None) -> set[str] | None:
    if allowed_hosts is None:
        return None
    normalized = {host.strip().lower().rstrip(".") for host in allowed_hosts if host.strip()}
    if not normalized:
        raise ValueError("allowed_hosts cannot be empty")
    return normalized


def validate_public_url(url: str, *, allowed_hosts: set[str] | None = None) -> str:
    """Validate a public HTTP(S) target before any network request.

    The adapter layer normally passes an explicit allow-list. Generic callers also
    reject credentials, unusual ports, localhost-style names and non-global literal IPs.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ValueError("invalid URL") from exc
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("absolute http(s) URL required")
    if parts.username is not None or parts.password is not None:
        raise VacancyEngineError("URL credentials are not allowed", FailureCategory.ACCESS_RESTRICTION)
    if port not in {None, 80, 443}:
        raise VacancyEngineError("non-standard network port is not allowed", FailureCategory.ACCESS_RESTRICTION)

    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("URL hostname required")
    normalized = _normalized_allowed_hosts(allowed_hosts)
    if normalized is not None and host not in normalized:
        raise VacancyEngineError(
            f"unexpected target host {host}",
            FailureCategory.UNEXPECTED_REDIRECT,
        )

    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES) or "." not in host:
        raise VacancyEngineError(
            f"non-public hostname {host}",
            FailureCategory.ACCESS_RESTRICTION,
        )
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise VacancyEngineError(
            f"non-public IP target {host}",
            FailureCategory.ACCESS_RESTRICTION,
        )
    return host


class PublicHttpClient:
    """Public HTTP client with bounded retries, redirect checks and failure mapping."""

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        attempts: int = 2,
        base_delay: float = 1.0,
        max_delay: float = 8.0,
        max_bytes: int = 5_000_000,
        max_redirects: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        opener: Any | None = None,
    ) -> None:
        if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 2:
            raise ValueError("attempts must be an integer between 1 and 2")
        for name, value, minimum in (
            ("timeout", timeout, 0.0),
            ("base_delay", base_delay, 0.0),
            ("max_delay", max_delay, 0.0),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= minimum:
                if name == "base_delay" and value == 0:
                    continue
                if name == "max_delay" and value == 0:
                    continue
                raise ValueError(f"{name} must be finite and {'> 0' if name == 'timeout' else '>= 0'}")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
            raise ValueError("max_bytes must be an integer >= 1")
        if isinstance(max_redirects, bool) or not isinstance(max_redirects, int) or max_redirects < 0 or max_redirects > 10:
            raise ValueError("max_redirects must be an integer between 0 and 10")
        self.timeout = float(timeout)
        self.attempts = attempts
        self.base_delay = float(base_delay)
        self.max_delay = float(max_delay)
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.sleep = sleep
        self.opener = opener or build_opener(ProxyHandler({}), _NoRedirect())

    def get_json(self, url: str, *, allowed_hosts: set[str] | None = None) -> Any:
        body = self.get_bytes(url, allowed_hosts=allowed_hosts)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VacancyEngineError(
                f"{url}: response is not valid UTF-8 JSON",
                FailureCategory.MALFORMED,
            ) from exc

    def get_text(self, url: str, *, allowed_hosts: set[str] | None = None) -> str:
        body = self.get_bytes(url, allowed_hosts=allowed_hosts)
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise VacancyEngineError(
                f"{url}: response is not valid UTF-8 text",
                FailureCategory.MALFORMED,
            ) from exc

    def get_bytes(self, url: str, *, allowed_hosts: set[str] | None = None) -> bytes:
        normalized_hosts = _normalized_allowed_hosts(allowed_hosts)
        current_url = url
        validate_public_url(current_url, allowed_hosts=normalized_hosts)
        redirects = 0
        transient_attempt = 1
        last_error: VacancyEngineError | None = None

        while True:
            req = Request(
                current_url,
                headers={
                    "Accept": "application/json,text/xml,application/xml,text/html;q=0.8,*/*;q=0.1",
                    "User-Agent": USER_AGENT,
                },
            )
            try:
                with self.opener.open(req, timeout=self.timeout) as response:
                    final_url = response.geturl()
                    validate_public_url(final_url, allowed_hosts=normalized_hosts)
                    content_length = response.headers.get("Content-Length")
                    if content_length and content_length.isdigit() and int(content_length) > self.max_bytes:
                        raise VacancyEngineError(
                            f"{current_url}: response exceeds max_bytes",
                            FailureCategory.MALFORMED,
                        )
                    data = response.read(self.max_bytes + 1)
                    if len(data) > self.max_bytes:
                        raise VacancyEngineError(
                            f"{current_url}: response exceeds max_bytes",
                            FailureCategory.MALFORMED,
                        )
                    return data
            except HTTPError as exc:
                status = int(exc.code)
                if status in REDIRECT_STATUSES:
                    if redirects >= self.max_redirects:
                        raise VacancyEngineError(
                            f"{current_url}: too many redirects",
                            FailureCategory.UNEXPECTED_REDIRECT,
                        ) from exc
                    location = exc.headers.get("Location")
                    if not location:
                        raise VacancyEngineError(
                            f"{current_url}: redirect without Location",
                            FailureCategory.MALFORMED,
                        ) from exc
                    target = urljoin(current_url, location)
                    if urlsplit(current_url).scheme == "https" and urlsplit(target).scheme != "https":
                        raise VacancyEngineError(
                            f"{current_url}: HTTPS downgrade redirect blocked",
                            FailureCategory.UNEXPECTED_REDIRECT,
                        ) from exc
                    validate_public_url(target, allowed_hosts=normalized_hosts)
                    current_url = target
                    redirects += 1
                    continue
                if status in BLOCKED_STATUSES:
                    raise VacancyEngineError(
                        f"{current_url}: access blocked with HTTP {status}",
                        FailureCategory.BLOCKED,
                        status,
                        False,
                    ) from exc
                if status == 404:
                    raise VacancyEngineError(
                        f"{current_url}: not found",
                        FailureCategory.NOT_FOUND,
                        status,
                        False,
                    ) from exc
                if status in RETRYABLE_STATUSES:
                    last_error = VacancyEngineError(
                        f"{current_url}: transient HTTP {status}",
                        FailureCategory.TRANSIENT,
                        status,
                        True,
                    )
                    if transient_attempt < self.attempts:
                        retry_after = _retry_after_seconds(exc.headers.get("Retry-After"), time.time())
                        delay = retry_after if retry_after is not None else self.base_delay * 2 ** (transient_attempt - 1)
                        self.sleep(min(delay, self.max_delay))
                        transient_attempt += 1
                        continue
                    raise last_error from exc
                raise VacancyEngineError(
                    f"{current_url}: HTTP {status}", FailureCategory.OTHER, status, False
                ) from exc
            except (TimeoutError, URLError, OSError) as exc:
                last_error = VacancyEngineError(
                    f"{current_url}: transient network failure: {exc}",
                    FailureCategory.TRANSIENT,
                    retryable=True,
                )
                if transient_attempt < self.attempts:
                    self.sleep(min(self.base_delay * 2 ** (transient_attempt - 1), self.max_delay))
                    transient_attempt += 1
                    continue
                raise last_error from exc
