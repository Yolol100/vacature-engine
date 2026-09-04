from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class FetchError(RuntimeError):
    def __init__(self, category: str, message: str, *, status: int | None = None):
        super().__init__(message)
        self.category = category
        self.status = status


@dataclass
class HttpClient:
    timeout_seconds: float = 20.0
    retries: int = 2
    max_response_bytes: int = 50 * 1024 * 1024
    user_agent: str = "Webactueel-Vacature-Ingestion/0.2"

    def _get_bytes(self, url: str, *, headers: dict[str, str] | None = None) -> bytes:
        attempts = max(0, int(self.retries)) + 1
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                req_headers = {"User-Agent": self.user_agent}
                if headers:
                    req_headers.update(headers)
                request = Request(url, headers=req_headers, method="GET")
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    status = getattr(response, "status", 200)
                    declared = response.headers.get("Content-Length")
                    if declared:
                        try:
                            if int(declared) > self.max_response_bytes:
                                raise FetchError(
                                    "response_too_large",
                                    f"declared response exceeds {self.max_response_bytes} bytes",
                                    status=status,
                                )
                        except ValueError:
                            pass
                    body = response.read(self.max_response_bytes + 1)
                    if len(body) > self.max_response_bytes:
                        raise FetchError(
                            "response_too_large",
                            f"response exceeds {self.max_response_bytes} bytes",
                            status=status,
                        )
                    return body
            except HTTPError as exc:
                last = exc
                if exc.code == 429:
                    category = "rate_limited"
                elif exc.code in {401, 403}:
                    category = "blocked_or_auth_required"
                elif 500 <= exc.code < 600:
                    category = "upstream_transient"
                else:
                    category = "http_error"
                if attempt + 1 >= attempts or exc.code not in {429, 500, 502, 503, 504}:
                    raise FetchError(category, f"HTTP {exc.code} for {url}", status=exc.code) from exc
            except (URLError, TimeoutError) as exc:
                last = exc
                if attempt + 1 >= attempts:
                    raise FetchError("timeout_or_network", f"network error for {url}: {exc}") from exc
            if attempt + 1 < attempts:
                delay = min(4.0, 0.25 * (2**attempt)) + random.random() * 0.1
                time.sleep(delay)
        raise FetchError("other_technical_failure", f"fetch failed: {last}")

    def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        req_headers = {"Accept": "application/json"}
        if headers:
            req_headers.update(headers)
        body = self._get_bytes(url, headers=req_headers)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FetchError("malformed_result", f"invalid JSON: {exc}") from exc

    def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        req_headers = {"Accept": "text/html,application/xhtml+xml,text/plain;q=0.8"}
        if headers:
            req_headers.update(headers)
        body = self._get_bytes(url, headers=req_headers)
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return body.decode("utf-8", errors="replace")
