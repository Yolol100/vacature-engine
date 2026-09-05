from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DESCRIPTION_EXCERPT_CHARS = 1200
REVIEW_QUEUE_PAGE_SIZE = 25
_COMPACT_FIELDS = (
    "source_id",
    "source_type",
    "source_instance",
    "source_job_id",
    "source_url",
    "url",
    "canonical_url",
    "apply_url",
    "employer",
    "title",
    "location",
    "remote",
    "listing_language",
    "published_at",
    "updated_at",
    "valid_through",
    "salary",
    "employment_type",
    "workplace_type",
    "content_hash",
    "source_metadata",
    "tags",
    "keywords",
    "first_seen_at",
    "last_seen_at",
    "ingestion_change",
)


def review_key(item: dict[str, Any]) -> str:
    source_id = str(item.get("source_id") or "").strip()
    source_job_id = str(item.get("source_job_id") or "").strip()
    canonical_url = str(item.get("canonical_url") or item.get("url") or "").strip()
    content_hash = str(item.get("content_hash") or "").strip()

    if source_id and source_job_id:
        identity = f"source:{source_id}:{source_job_id}"
    elif canonical_url:
        identity = f"url:{canonical_url}"
    else:
        identity = "payload:" + json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    digest = hashlib.sha256(f"{identity}\0{content_hash}".encode("utf-8")).hexdigest()
    return f"review:{digest}"


def _description_excerpt(value: Any) -> str | None:
    if value is None:
        return None
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return text[:DESCRIPTION_EXCERPT_CHARS]


def compact_review_item(value: dict[str, Any]) -> dict[str, Any]:
    item = {field: value.get(field) for field in _COMPACT_FIELDS if value.get(field) is not None}
    excerpt = _description_excerpt(value.get("description") or value.get("description_excerpt"))
    if excerpt:
        item["description_excerpt"] = excerpt
    return item


def _acked_keys(ack_doc: dict[str, Any] | None) -> set[str]:
    if not isinstance(ack_doc, dict):
        return set()
    raw = ack_doc.get("acked_keys", [])
    if not isinstance(raw, list):
        return set()
    return {str(value) for value in raw if value}


def _queue_items(document: dict[str, Any] | None, *, current: bool = False) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    raw = document.get("review_queue", [])
    if not isinstance(raw, list):
        return []
    run_id = str(document.get("run_id") or "")
    completed_at = str(document.get("completed_at") or "")
    out: list[dict[str, Any]] = []
    for value in raw:
        if not isinstance(value, dict):
            continue
        key = str(value.get("review_key") or review_key(value))
        item = compact_review_item(value)
        item.setdefault("origin_run_id", str(value.get("origin_run_id") or run_id))
        item.setdefault("origin_completed_at", str(value.get("origin_completed_at") or completed_at))
        item["review_key"] = key
        if current:
            item["queue_seen_in_current_run"] = True
        out.append(item)
    return out


def build_review_queue(
    current_doc: dict[str, Any],
    *,
    previous_doc: dict[str, Any] | None = None,
    ack_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    acked = _acked_keys(ack_doc)
    merged: dict[str, dict[str, Any]] = {}

    for item in _queue_items(previous_doc):
        key = str(item["review_key"])
        if key not in acked:
            merged[key] = item

    for item in _queue_items(current_doc, current=True):
        key = str(item["review_key"])
        if key not in acked:
            merged[key] = item

    queue = list(merged.values())
    queue.sort(key=lambda item: (str(item.get("origin_completed_at") or ""), str(item.get("review_key") or "")))

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": current_doc.get("run_id"),
        "completed_at": current_doc.get("completed_at"),
        "review_queue_count": len(queue),
        "review_queue": queue,
    }


def write_review_queue_pages(
    document: dict[str, Any],
    *,
    directory: str | Path,
    index_path: str | Path,
    page_size: int = REVIEW_QUEUE_PAGE_SIZE,
    path_prefix: str = "review-queue-pages",
) -> dict[str, Any]:
    if page_size < 1:
        raise ValueError("page_size must be >= 1")
    page_dir = Path(directory)
    page_dir.mkdir(parents=True, exist_ok=True)
    for stale in page_dir.glob("page-*.json"):
        stale.unlink()

    raw = document.get("review_queue", []) if isinstance(document, dict) else []
    items = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    total_pages = (len(items) + page_size - 1) // page_size
    pages: list[dict[str, Any]] = []

    for page_index in range(total_pages):
        start = page_index * page_size
        page_items = items[start:start + page_size]
        filename = f"page-{page_index + 1:04d}.json"
        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": document.get("run_id"),
            "completed_at": document.get("completed_at"),
            "page": page_index + 1,
            "total_pages": total_pages,
            "review_queue_count": len(items),
            "page_item_count": len(page_items),
            "review_queue": page_items,
        }
        (page_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        pages.append({
            "page": page_index + 1,
            "path": f"{path_prefix}/{filename}",
            "count": len(page_items),
            "first_review_key": str(page_items[0].get("review_key") or "") if page_items else "",
            "last_review_key": str(page_items[-1].get("review_key") or "") if page_items else "",
        })

    index = {
        "schema_version": SCHEMA_VERSION,
        "run_id": document.get("run_id"),
        "completed_at": document.get("completed_at"),
        "review_queue_count": len(items),
        "page_size": page_size,
        "total_pages": total_pages,
        "pages": pages,
    }
    Path(index_path).write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return index


def empty_ack_document() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "acked_keys": [], "migrations": []}
