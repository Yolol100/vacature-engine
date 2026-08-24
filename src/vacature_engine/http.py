from __future__ import annotations

import json
import time
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from .errors import FailureCategory, VacancyEngineError

USER_AGENT = "vacature-engine/3.0 (+public vacancy verification; no access-control bypass)"
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
BLOCKED_STATUSES = {401, 403, 406}


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


class PublicHttpClient:
    """Small public HTTP client with bounded retries and explicit failure mapping.

    It intentionally disables proxy auto-discovery and never escalates blocked
    requests to stealth clients, VPNs, rotating proxies or login sessions.
    """

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 8.0,
        max_bytes: int = 5_000_000,
        sleep: Callable[[float], None] = time.sleep,
        opener: Any | None = None,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be >= 1")
        self.timeout = timeout
        self.attempts = attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_bytes = max_bytes
        self.sleep = sleep
        self.opener = opener or build_opener(ProxyHandler({}))

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
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("absolute http(s) URL required")

        last_error: VacancyEngineError | None = None
        for attempt in range(1, self.attempts + 1):
            req = Request(
                url,
                headers={
                    "Accept": "application/json,text/xml,application/xml,text/html;q=0.8,*/*;q=0.1",
                    "User-Agent": USER_AGENT,
                },
            )
            try:
                with self.opener.open(req, timeout=self.timeout) as response:
                    final_url = response.geturl()
                    self._validate_final_host(final_url, allowed_hosts)
                    content_length = response.headers.get("Content-Length")
                    if content_length and content_length.isdigit() and int(content_length) > self.max_bytes:
                        raise VacancyEngineError(
                            f"{url}: response exceeds max_bytes",
                            FailureCategory.MALFORMED,
                        )
                    data = response.read(self.max_bytes + 1)
                    if len(data) > self.max_bytes:
                        raise VacancyEngineError(
                            f"{url}: response exceeds max_bytes",
                            FailureCategory.MALFORMED,
                        )
                    return data
            except HTTPError as exc:
                status = int(exc.code)
                if status in BLOCKED_STATUSES:
                    raise VacancyEngineError(
                        f"{url}: access blocked with HTTP {status}",
                        FailureCategory.BLOCKED,
                        status,
                        False,
                    ) from exc
                if status == 404:
                    raise VacancyEngineError(
                        f"{url}: not found",
                        FailureCategory.NOT_FOUND,
                        status,
                        False,
                    ) from exc
                if status in RETRYABLE_STATUSES:
                    last_error = VacancyEngineError(
                        f"{url}: transient HTTP {status}",
                        FailureCategory.TRANSIENT,
                        status,
                        True,
                    )
                    if attempt < self.attempts:
                        retry_after = _retry_after_seconds(exc.headers.get("Retry-After"), time.time())
                        delay = retry_after if retry_after is not None else self.base_delay * 2 ** (attempt - 1)
                        self.sleep(min(delay, self.max_delay))
                        continue
                    raise last_error from exc
                raise VacancyEngineError(
                    f"{url}: HTTP {status}", FailureCategory.OTHER, status, False
                ) from exc
            except (TimeoutError, URLError, OSError) as exc:
                last_error = VacancyEngineError(
                    f"{url}: transient network failure: {exc}",
                    FailureCategory.TRANSIENT,
                    retryable=True,
                )
                if attempt < self.attempts:
                    self.sleep(min(self.base_delay * 2 ** (attempt - 1), self.max_delay))
                    continue
                raise last_error from exc
        raise last_error or VacancyEngineError(f"{url}: request failed")

    @staticmethod
    def _validate_final_host(final_url: str, allowed_hosts: set[str] | None) -> None:
        if not allowed_hosts:
            return
        host = (urlsplit(final_url).hostname or "").lower()
        normalized = {h.lower() for h in allowed_hosts}
        if host not in normalized:
            raise VacancyEngineError(
                f"unexpected redirect to {host or '<empty-host>'}",
                FailureCategory.UNEXPECTED_REDIRECT,
            )
