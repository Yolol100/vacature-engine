from __future__ import annotations

import hashlib
import json
from typing import Any


SCHEMA_VERSION = 1


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
        item = dict(value)
        item.setdefault("origin_run_id", run_id)
        item.setdefault("origin_completed_at", completed_at)
        item["review_key"] = review_key(item)
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


def empty_ack_document() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "acked_keys": []}
