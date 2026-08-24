from __future__ import annotations

import json
from html.parser import HTMLParser
from typing import Any

_NL_NAMES = {"nl", "nld", "netherlands", "the netherlands", "nederland"}
_MAX_JSONLD_CHARS = 1_000_000


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_jsonld = False
        self._chunks: list[str] = []
        self._chars = 0
        self._oversized = False
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        values = {k.lower(): (v or "") for k, v in attrs}
        if "ld+json" in values.get("type", "").lower():
            self._in_jsonld = True
            self._chunks = []
            self._chars = 0
            self._oversized = False

    def handle_data(self, data: str) -> None:
        if self._in_jsonld and not self._oversized:
            self._chars += len(data)
            if self._chars > _MAX_JSONLD_CHARS:
                self._chunks = []
                self._oversized = True
            else:
                self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_jsonld:
            block = "".join(self._chunks).strip() if not self._oversized else ""
            if block:
                self.blocks.append(block)
            self._in_jsonld = False
            self._chunks = []


def _is_jobposting(value: dict[str, Any]) -> bool:
    kind = value.get("@type")
    if isinstance(kind, str):
        return kind.lower() == "jobposting"
    if isinstance(kind, list):
        return any(isinstance(item, str) and item.lower() == "jobposting" for item in kind)
    return False


def _walk(value: Any):
    if isinstance(value, dict):
        if _is_jobposting(value):
            yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def extract_jobposting_jsonld(html: str) -> list[dict[str, Any]]:
    parser = _JsonLdParser()
    parser.feed(html)
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in parser.blocks:
        try:
            payload = json.loads(block)
        except (json.JSONDecodeError, RecursionError):
            continue
        try:
            postings = list(_walk(payload))
        except RecursionError:
            continue
        for posting in postings:
            try:
                marker = json.dumps(posting, sort_keys=True, ensure_ascii=False)
            except (TypeError, ValueError, RecursionError):
                continue
            if marker not in seen:
                result.append(posting)
                seen.add(marker)
    return result


def _name(value: object) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        for key in ("name", "addressCountry"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
    return None


def _collect_location_names(value: object) -> list[str]:
    names: list[str] = []
    if isinstance(value, list):
        for item in value:
            names.extend(_collect_location_names(item))
    elif isinstance(value, dict):
        direct = _name(value)
        if direct:
            names.append(direct)
        address = value.get("address")
        if isinstance(address, dict):
            country = _name(address.get("addressCountry"))
            if country:
                names.append(country)
        for key in ("geo", "containedInPlace"):
            if key in value:
                names.extend(_collect_location_names(value[key]))
    elif isinstance(value, str) and value.strip():
        names.append(value.strip())
    return list(dict.fromkeys(names))


def jobposting_facts(html: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for posting in extract_jobposting_jsonld(html):
        location_type = posting.get("jobLocationType")
        types = location_type if isinstance(location_type, list) else [location_type]
        fully_remote_signal = any(
            isinstance(value, str) and value.upper() == "TELECOMMUTE" for value in types
        )
        applicant_locations = _collect_location_names(posting.get("applicantLocationRequirements"))
        normalized_locations = {value.strip().lower() for value in applicant_locations}
        employer = None
        organization = posting.get("hiringOrganization")
        if isinstance(organization, dict):
            employer = _name(organization)
        facts.append(
            {
                "title": _name(posting.get("title")),
                "employer": employer,
                "date_posted": _name(posting.get("datePosted")),
                "valid_through": _name(posting.get("validThrough")),
                "fully_remote_signal": fully_remote_signal,
                "applicant_locations": applicant_locations,
                "netherlands_explicit": bool(normalized_locations & _NL_NAMES),
                "job_locations": _collect_location_names(posting.get("jobLocation")),
            }
        )
    return facts
