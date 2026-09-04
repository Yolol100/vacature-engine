from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Mapping

from .normalize import clean_text, normalize_canonical_url

_HASH_FIELDS = (
    "title", "employer", "location", "description", "employment_type",
    "salary", "apply_url", "remote", "workplace_type", "listing_language",
)


def _normalized(value: Any) -> Any:
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, Mapping):
        return {str(k): _normalized(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_normalized(v) for v in value]
    return value


def content_hash(row: Mapping[str, Any]) -> str:
    selected = {field: _normalized(row.get(field)) for field in _HASH_FIELDS}
    if selected.get("apply_url"):
        selected["apply_url"] = normalize_canonical_url(selected["apply_url"]) or selected["apply_url"]
    payload = json.dumps(selected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()
