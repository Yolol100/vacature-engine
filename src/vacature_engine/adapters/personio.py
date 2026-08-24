from __future__ import annotations

from html import unescape
import re
from urllib.parse import quote
from xml.etree import ElementTree

from .base import AdapterRegistry, BaseAdapter
from ..models import JobRecord

_TAGS = re.compile(r"<[^>]+>")


def _text(node: ElementTree.Element, name: str) -> str | None:
    found = node.find(name)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def _description(position: ElementTree.Element) -> str | None:
    parts: list[str] = []
    for desc in position.findall("./jobDescriptions/jobDescription"):
        name = _text(desc, "name")
        value = _text(desc, "value")
        if value:
            clean = re.sub(r"\s+", " ", unescape(_TAGS.sub(" ", value))).strip()
            parts.append(f"{name}: {clean}" if name else clean)
    return "\n\n".join(parts) or None


@AdapterRegistry.register
class PersonioAdapter(BaseAdapter):
    source = "personio"

    def __init__(self, slug: str, *, language: str = "en", **kwargs: object) -> None:
        super().__init__(slug, **kwargs)
        if language not in {"de", "en", "fr", "es", "nl", "it", "pt"}:
            raise ValueError("unsupported Personio language")
        self.language = language

    def fetch(self) -> list[JobRecord]:
        host = f"{self.slug}.jobs.personio.de"
        feed_url = f"https://{host}/xml?language={quote(self.language, safe='')}"
        xml = self.client.get_text(feed_url, allowed_hosts={host})
        try:
            root = ElementTree.fromstring(xml)
        except ElementTree.ParseError as exc:
            raise ValueError("personio XML could not be parsed") from exc
        result: list[JobRecord] = []
        for position in root.findall(".//position"):
            source_id = _text(position, "id") or ""
            title = _text(position, "name") or ""
            result.append(
                JobRecord(
                    source=self.source,
                    source_job_id=source_id,
                    title=title,
                    employer=self.slug,
                    job_url=feed_url,
                    location=_text(position, "office"),
                    employment_type=_text(position, "employmentType"),
                    department=_text(position, "department"),
                    description=_description(position),
                    posted_at=None,
                    raw={
                        "subcompany": _text(position, "subcompany"),
                        "recruiting_category": _text(position, "recruitingCategory"),
                        "requires_canonical_job_resolution": True,
                    },
                )
            )
        return [j for j in result if j.source_job_id and j.title]
