from __future__ import annotations

def extract_public_html(html: str, url: str) -> str:
    """Extract main text/metadata from already-fetched public HTML."""
    try:
        from trafilatura import extract
    except ImportError as exc:
        raise RuntimeError("Install optional dependency: pip install trafilatura") from exc
    result = extract(html, url=url, output_format="markdown", with_metadata=True,
                     include_comments=False, include_tables=True)
    if not result:
        raise ValueError("no extractable main content")
    return result

def render_public_page(url: str, timeout_ms: int = 20000) -> str:
    """Render a public JS page. Never use for login/CAPTCHA/access-control bypass."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("public http(s) URL required")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Install optional dependency: pip install playwright") from exc
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        html = page.content()
        browser.close()
        return html
