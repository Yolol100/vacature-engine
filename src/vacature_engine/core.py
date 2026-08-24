from __future__ import annotations

import hashlib
import ipaddress
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING = {
    "gclid",
    "fbclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
    "src",
    "campaign",
    "tracking",
    "trk",
    "trackingid",
    "tracking_id",
}


def canonical_url(url: str) -> str:
    p = urlsplit(url.strip())
    if p.scheme.lower() not in {"http", "https"} or not p.netloc:
        raise ValueError("absolute http(s) URL required")
    if p.username is not None or p.password is not None:
        raise ValueError("URL credentials are not allowed")
    host = (p.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("URL hostname required")
    try:
        if ipaddress.ip_address(host).version == 6:
            host = f"[{host}]"
    except ValueError:
        pass
    port = p.port
    if port and not (
        (p.scheme.lower() == "http" and port == 80)
        or (p.scheme.lower() == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", p.path or "/")
    if path != "/":
        path = path.rstrip("/")
    q = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if not (k.lower().startswith("utm_") or k.lower() in TRACKING)
    ]
    q.sort(key=lambda x: (x[0].lower(), x[1]))
    return urlunsplit((p.scheme.lower(), host, path, urlencode(q, doseq=True), ""))


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower().strip()
    value = re.sub(r"[^\w+#./-]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip(" .,_-/")
    if not value:
        raise ValueError("value cannot normalize to empty")
    return value


def vacancy_id(employer: str, title: str, url: str) -> str:
    material = f"{norm(employer)}|{norm(title)}|{canonical_url(url)}".encode()
    return hashlib.sha256(material).hexdigest()[:16]


def content_hash(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ValueError("content required")
    return hashlib.sha256(text.encode()).hexdigest()[:16]
