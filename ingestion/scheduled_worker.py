#!/usr/bin/env python3
"""Public-only scheduled vacancy discovery. No Google credentials, applications or private data."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from ipaddress import ip_address
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BODY = 350_000
MAX_OUTPUT_LEADS = 150
HEADERS = {"User-Agent": "VacatureRadar/1.0 (+public vacancies; no credentials)", "Accept": "text/html,application/ld+json"}
ROLE = re.compile(r"\b(wordpress|woocommerce|elementor|gutenberg|acf|web[\s-]?design|web[\s-]?develop|front[\s-]?end|frontend|website|webshop)\b", re.I)
REMOTE = re.compile(r"\b(fully remote|100%\s*remote|remote\b|work from anywhere|telecommut)", re.I)
NONREMOTE = re.compile(r"\b(hybrid|on[\s-]?site|in office|office[\s-]?based|not remote|no remote)\b", re.I)
REGION_BLOCK = re.compile(r"\b(us only|usa only|united states only|uk only|u\.s\.\s*only|w2 only)\b", re.I)
BAD_ROLE = re.compile(r"\b(ai automation|automation engineer|sales engineer|systems engineer|product manager|mobile developer|data engineer)\b", re.I)
PRIVATE_NAMES = re.compile(r"(^localhost$|(^|\.)local$|(^|\.)internal$)", re.I)
CAREERS_ROOT = re.compile(r"^/(?:careers?|jobs?|openings?|vacancies|about/careers?)/?$", re.I)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 1600 or re.search(r"[\s\x00-\x1f<>\\]", url):
        return ""
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return ""
        if parsed.port not in (None, 443):
            return ""
        host = parsed.hostname.lower()
        if PRIVATE_NAMES.search(host) or host.endswith(".invalid"):
            return ""
        try:
            ip_address(host)
            return ""
        except ValueError:
            pass
        if "." not in host:
            return ""
        return urlunparse(("https", parsed.netloc.lower(), parsed.path or "/", "", parsed.query, ""))
    except (ValueError, UnicodeError):
        return ""


def job_url(href: str, base: str) -> str:
    if not isinstance(href, str):
        return ""
    if href.startswith("/url?"):
        href = parse_qs(urlparse(href).query).get("q", [""])[0]
    if href.startswith("//"):
        href = "https:" + href
    elif href.startswith("/"):
        href = urljoin(base, href)
    parsed = safe_url(href)
    if not parsed:
        return ""
    components = urlparse(parsed)
    filtered = "&".join(
        x for x in components.query.split("&")
        if x and not re.match(r"(utm_|gclid=|fbclid=|msclkid=)", x, re.I)
    )
    return urlunparse(components._replace(query=filtered, fragment="")).rstrip("/")


def relevant(title: str, desc: str = "") -> bool:
    title = (title or "").strip()[:200]
    return bool(ROLE.search(title) and not (BAD_ROLE.search(title) and not
                re.search(r"wordpress|woocommerce|elementor|gutenberg", title, re.I)))


def remote_signal(title: str, description: str, location: str, explicit: bool = False) -> bool:
    evidence = " ".join((title or "", description or "", location or ""))[:5500]
    return bool((explicit or REMOTE.search(evidence)) and
                not NONREMOTE.search(evidence) and not REGION_BLOCK.search(evidence))


class PublicHtmlParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._script = False
        self._link: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs)
        if tag == "script" and str(attrs.get("type") or "").lower().startswith("application/ld+json"):
            self._script = True
            self._buf = []
        elif tag == "a" and attrs.get("href") and not self._script:
            self._link = attrs["href"]
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._script or self._link:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script:
            self.scripts.append("".join(self._buf))
            self._script = False
            self._buf = []
        elif tag == "a" and self._link:
            self.links.append((self._link, " ".join(self._buf)))
            self._link = None
            self._buf = []


def discover(html: str, source: dict, from_url: str) -> list[dict]:
    parser = PublicHtmlParser()
    try:
        parser.feed(html[:MAX_BODY])
    except Exception:
        pass
    out: list[dict] = []
    seen: set[str] = set()

    def add(url: str, title: str, description: str, location: str, date: str,
            employer: str, evidence: str, explicit_remote: bool = False) -> None:
        link = job_url(url, from_url)
        if not link or not relevant(title, description) or not remote_signal(
                title, description, location, explicit_remote):
            return
        if CAREERS_ROOT.match(urlparse(link).path):
            return
        if link in seen or len(out) >= 12:
            return
        seen.add(link)
        out.append({
            "source_id": source["source_id"], "source_type": source["source_type"],
            "job_id": link, "employer": (employer or source.get("source_name") or "")[:120],
            "title": str(title).strip()[:180], "url": link,
            "published_hint": str(date or "")[:40],
            "location": (str(location or "Remote") if explicit_remote else str(location or "Remote"))[:200],
            "description": str(description or "")[:800],
            "evidence": evidence, "review_status": "unverified"
        })

    def visit(node: object, depth: int = 0) -> None:
        if depth > 6 or len(out) >= 12:
            return
        if isinstance(node, list):
            for child in node[:50]:
                visit(child, depth + 1)
        elif isinstance(node, dict):
            kinds = node.get("@type", [])
            kinds = [kinds] if isinstance(kinds, str) else kinds if isinstance(kinds, list) else []
            if "JobPosting" in kinds:
                org = node.get("hiringOrganization") or {}
                org = org if isinstance(org, dict) else {}
                location = node.get("applicantLocationRequirements") or {}
                location = location[0] if isinstance(location, list) and location else location
                if isinstance(location, dict):
                    place = str(location.get("name") or location.get("addressCountry") or "")
                else:
                    place = str(location or "")
                remote = "TELECOMMUTE" in str(node.get("jobLocationType") or "").upper()
                add(str(node.get("url") or ""), str(node.get("title") or ""),
                    re.sub("<[^>]+>", " ", str(node.get("description") or "")),
                    ("Remote - " + place) if remote and place else "Remote" if remote else place,
                    str(node.get("datePosted") or ""), str(org.get("name") or ""),
                    "JobPosting JSON-LD; original date/NL eligibility unverified", remote)
            for key in ("@graph", "mainEntity", "itemListElement"):
                if key in node:
                    visit(node[key], depth + 1)

    # Public APIs and RSS feeds are not HTML, and many registry sources expose
    # useful role listings only via these structured formats.
    stripped = str(html or "").lstrip()
    if stripped.startswith(("{", "[")):
        try:
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                items = (payload.get("jobs") or payload.get("data") or
                         payload.get("results") or payload.get("content") or
                         payload.get("postings") or [])
            else:
                items = payload
            if isinstance(items, dict):
                items = items.get("jobs") or items.get("items") or []
            for item in (items[:75] if isinstance(items, list) else []):
                if not isinstance(item, dict):
                    continue
                loc = (item.get("candidate_required_location") or item.get("jobGeo") or
                       item.get("location") or item.get("locations") or "")
                if isinstance(loc, dict):
                    loc = loc.get("name") or loc.get("location_str") or loc.get("country") or ""
                if isinstance(loc, list):
                    loc = ", ".join(str(v.get("name", "")) if isinstance(v, dict) else str(v)
                                    for v in loc[:5])
                desc = str(item.get("description") or item.get("jobDescription") or
                           item.get("content") or "")
                remote = item.get("remote") is True or item.get("isRemote") is True or (
                    item.get("telecommuting") is True)
                place = ("Remote - " + str(loc)) if remote and loc else "Remote" if remote else str(loc)
                employer = item.get("company") or item.get("company_name") or item.get("companyName") or ""
                if isinstance(employer, dict):
                    employer = employer.get("name") or ""
                add(str(item.get("url") or item.get("job_url") or item.get("jobUrl") or
                        item.get("apply_url") or item.get("applicationLink") or ""),
                    str(item.get("title") or item.get("jobTitle") or item.get("name") or
                        item.get("position") or ""),
                    re.sub("<[^>]+>", " ", desc), place,
                    str(item.get("publication_date") or item.get("pubDate") or
                        item.get("posted_at") or ""), str(employer),
                    "Public API job listing; employer/original date/NL eligibility unverified", remote)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    if "<rss" in stripped[:250] or "<feed" in stripped[:250]:
        try:
            root = ET.fromstring(stripped)
            for node in list(root.iter())[:200]:
                tag = node.tag.split("}")[-1].lower()
                if tag not in ("item", "entry"):
                    continue
                fields = {}
                for child in node:
                    key = child.tag.split("}")[-1].lower()
                    fields[key] = child.text or child.attrib.get("href", "")
                add(fields.get("link", ""), fields.get("title", ""),
                    re.sub("<[^>]+>", " ", fields.get("description") or fields.get("summary") or ""),
                    "", fields.get("pubdate", "") or fields.get("published", ""),
                    source.get("source_name", ""),
                    "Public RSS listing; employer/original date/NL eligibility unverified")
        except ET.ParseError:
            pass
    for chunk in parser.scripts[:60]:
        try:
            visit(json.loads(chunk))
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    for href, label in parser.links[:3000]:
        title = " ".join(label.split())[:180]
        if not remote_signal(title, "", "") or not relevant(title):
            continue
        add(href, title, "", "Remote", "", source.get("source_name", ""),
            "Explicit remote role in public link text; employer/date/NL unverified")
    return out


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = build_opener(NoRedirect)


def fetch_public(url: str, timeout: int = 8) -> tuple[str, str, str]:
    checked = safe_url(url)
    if not checked:
        return "invalid", "", url
    current = checked
    for _ in range(3):
        try:
            request = Request(current, headers=HEADERS, method="GET")
            with OPENER.open(request, timeout=timeout) as response:
                content_type = (response.headers.get("Content-Type") or "").lower()
                if not any(x in content_type for x in ("html", "json", "xml", "text")):
                    return "unsupported_content", "", current
                data = response.read(MAX_BODY + 1)
                if len(data) > MAX_BODY:
                    data = data[:MAX_BODY]
                return "http_200", data.decode("utf-8", errors="replace"), current
        except HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                target = safe_url(urljoin(current, error.headers.get("Location", "")))
                if not target:
                    return "unsafe_redirect", "", current
                current = target
                continue
            return "http_" + str(error.code), "", current
        except (URLError, TimeoutError, OSError, ValueError):
            return "request_failed", "", current
    return "redirect_limit", "", current


def render_with_chrome(url: str, chrome: str, timeout: int = 12) -> tuple[str, str]:
    if not chrome or not safe_url(url):
        return "browser_unavailable", ""
    with tempfile.TemporaryDirectory(prefix="radar-chrome-") as profile:
        argv = [chrome, "--headless=new", "--disable-gpu", "--disable-dev-shm-usage",
                "--no-first-run", "--no-default-browser-check", "--disable-extensions",
                "--disable-background-networking", "--disable-sync",
                "--no-sandbox", "--virtual-time-budget=2500",
                "--user-data-dir=" + profile, "--dump-dom", url]
        environment = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
                       if k in os.environ}
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout, env=environment, check=False,
                                  encoding="utf-8", errors="replace")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return "browser_timeout_or_unavailable", ""
        html = proc.stdout[:MAX_BODY]
        if "<html" not in html.lower():
            return "browser_no_html", ""
        if "captcha" in html[:5000].lower() or "unusual traffic" in html[:5000].lower():
            return "browser_blocked", ""
        return "rendered", html


def source_check(src: dict) -> tuple[dict, list[dict]]:
    now = utc_now()
    status, html, final_url = fetch_public(src["base_url"])
    observations = discover(html, src, final_url) if status == "http_200" else []
    return {
        "source_id": src["source_id"], "status": status,
        "checked_at": now, "browser": "not_attempted",
        "candidate_count": len(observations),
        "coverage": "public_response_only" if status == "http_200" else "blocked_or_failed",
        "url": src["base_url"]
    }, observations


def discover_google(query: str, index: int, chrome: str | None) -> tuple[dict, list[dict]]:
    url = "https://www.google.com/search?q=" + quote(query, safe="") + "&tbs=qdr:w"
    source = {"source_id": "google-jobs", "source_name": "Google public discovery",
              "source_type": "discovery"}
    status, html, _ = fetch_public(url)
    browser = "not_needed"
    if status != "http_200" or not discover(html, source, url):
        if chrome:
            browser, rendered = render_with_chrome(url, chrome)
            if browser == "rendered":
                html = rendered
    leads = discover(html, source, url)
    return {"query": query, "status": status, "browser": browser,
            "candidate_count": len(leads), "search_index": index}, leads


def run(registry_path: Path, output_path: Path, *, limit: int = 0,
        chrome: str | None = None, max_render: int = 90, google: bool = True) -> dict:
    start = time.monotonic()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = registry["entries"]
    assert len(entries) == registry["count"] and len({s["source_id"] for s in entries}) == len(entries)
    for src in entries:
        assert safe_url(src["base_url"]), src["source_id"]
    checked = entries[:limit] if limit else entries
    statuses: dict[str, dict] = {}
    jobs: list[dict] = []
    with ThreadPoolExecutor(max_workers=14) as pool:
        tasks = {pool.submit(source_check, src): src for src in checked}
        for f in as_completed(tasks):
            src = tasks[f]
            try:
                status, found = f.result()
            except Exception:
                status, found = {"source_id": src["source_id"], "status": "unexpected_error",
                                 "checked_at": utc_now(), "browser": "not_attempted",
                                 "candidate_count": 0, "coverage": "error", "url": src["base_url"]}, []
            statuses[src["source_id"]] = status
            jobs.extend(found)
    chrome = None if max_render == 0 else (chrome or shutil.which("google-chrome") or shutil.which("google-chrome-stable"))
    if os.name == "nt" and not chrome:
        path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        chrome = path if os.path.isfile(path) else None
    # Round robin browser sampling across all remaining JS-dependent sources.
    choices = [s for s in checked if statuses[s["source_id"]]["status"] == "http_200" and
               not statuses[s["source_id"]]["candidate_count"]]
    epoch = int(time.time() // 1800)
    if choices:
        offset = (epoch * max_render) % len(choices)
        choices = (choices[offset:] + choices[:offset])[:max_render]
    if chrome and choices:
        with ThreadPoolExecutor(max_workers=3) as pool:
            renders = {pool.submit(render_with_chrome, s["base_url"], chrome): s for s in choices}
            for f in as_completed(renders):
                src = renders[f]
                try:
                    state, html = f.result()
                except Exception:
                    state, html = "browser_failed", ""
                found = discover(html, src, src["base_url"]) if state == "rendered" else []
                statuses[src["source_id"]]["browser"] = state
                statuses[src["source_id"]]["candidate_count"] += len(found)
                if state == "rendered":
                    statuses[src["source_id"]]["coverage"] = "rendered_public_page_only"
                jobs.extend(found)
    for src in entries:
        if src["source_id"] not in statuses:
            statuses[src["source_id"]] = {
                "source_id": src["source_id"], "status": "not_attempted_test_limit",
                "checked_at": "", "browser": "not_attempted", "candidate_count": 0,
                "coverage": "not_checked", "url": src["base_url"]
            }
    google_log: list[dict] = []
    if google:
        searches = [
            'remote WordPress WooCommerce developer job',
            'remote Elementor web designer jobs Europe',
            'fully remote frontend website developer job Netherlands',
            'site:jobs.ashbyhq.com "WordPress" "remote" jobs',
            'site:boards.greenhouse.io "WordPress" "remote"'
        ]
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(discover_google, q, i, chrome): q for i, q in enumerate(searches)}
            for future in as_completed(futures):
                try:
                    status, found = future.result()
                except Exception:
                    status, found = {"query": futures[future], "status": "error", "candidate_count": 0}, []
                google_log.append(status)
                jobs.extend(found)
    unique: dict[str, dict] = {}
    for job in jobs:
        key = job_url(job.get("url", ""), "https://example.com/")
        if key and (key not in unique or (job.get("evidence") or "").startswith("JobPosting")):
            unique[key] = job
    report = {
        "schema_version": 1, "generated_at": utc_now(),
        "registry_snapshot_date": registry["snapshotted_at"],
        "source_count": len(entries),
        "sources": [statuses[src["source_id"]] for src in entries],
        "google": sorted(google_log, key=lambda a: a.get("search_index", 0)),
        "observations": list(unique.values())[:MAX_OUTPUT_LEADS],
        "summary": {
            "registered": len(entries),
            "attempted": sum(bool(x["checked_at"]) for x in statuses.values()),
            "http_ok": sum(x["status"] == "http_200" for x in statuses.values()),
            "browser_rendered": sum(x["browser"] == "rendered" for x in statuses.values()),
            "discovered": len(unique),
            "saved_in_report": min(len(unique), MAX_OUTPUT_LEADS),
            "elapsed_sec": round(time.monotonic() - start, 2)
        }
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n",
                           encoding="utf-8")
    return report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--registry", default="ingestion/sources.public-snapshot.json")
    p.add_argument("--output", default="worker/latest.json")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--max-render", type=int, default=90)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--no-google", action="store_true")
    a = p.parse_args()
    result = run(Path(a.registry), Path(a.output), limit=a.limit,
                 chrome="" if a.no_browser else None, max_render=0 if a.no_browser else a.max_render,
                 google=not a.no_google)
    print(json.dumps({"status": "completed", **result["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
