from __future__ import annotations

from urllib.parse import urlsplit

from .http import validate_public_url


def extract_public_html(html: str, url: str) -> str:
    """Extract main text/metadata from already-fetched public HTML."""
    try:
        from trafilatura import extract
    except ImportError as exc:
        raise RuntimeError("Install optional dependency: pip install trafilatura") from exc
    result = extract(
        html,
        url=url,
        output_format="markdown",
        with_metadata=True,
        include_comments=False,
        include_tables=True,
    )
    if not result:
        raise ValueError("no extractable main content")
    return result


def render_public_page(url: str, timeout_ms: int = 20000) -> str:
    """Render one public page while blocking cross-host navigation and local targets."""
    host = validate_public_url(url)
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms < 1000 or timeout_ms > 120000:
        raise ValueError("timeout_ms must be an integer between 1000 and 120000")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Install optional dependency: pip install playwright") from exc

    allowed = {host}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()

            def route_handler(route, request):  # type: ignore[no-untyped-def]
                try:
                    if request.url.startswith(("http://", "https://")):
                        validate_public_url(
                            request.url,
                            allowed_hosts=allowed if request.is_navigation_request() else None,
                        )
                except (ValueError, RuntimeError):
                    route.abort()
                    return
                route.continue_()

            page.route("**/*", route_handler)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            final_host = (urlsplit(page.url).hostname or "").lower()
            validate_public_url(page.url, allowed_hosts=allowed)
            if final_host != host:
                raise RuntimeError("cross-host browser navigation blocked")
            return page.content()
        finally:
            browser.close()
