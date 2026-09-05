from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _timestamp(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("timestamp is required")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_review_backlog(
    state_path: str | Path,
    *,
    since: str,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    threshold = _timestamp(since)
    db = sqlite3.connect(str(state_path))
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT job_id,payload_json,status,first_seen_at,last_seen_at FROM jobs ORDER BY first_seen_at,job_id"
        ).fetchall()
    finally:
        db.close()

    out: list[dict[str, Any]] = []
    for row in rows:
        if active_only and str(row["status"] or "") != "active":
            continue
        try:
            first_seen = _timestamp(str(row["first_seen_at"] or ""))
        except (TypeError, ValueError):
            continue
        if first_seen < threshold:
            continue
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        item = dict(payload)
        item["first_seen_at"] = str(row["first_seen_at"] or item.get("first_seen_at") or "")
        item["last_seen_at"] = str(row["last_seen_at"] or item.get("last_seen_at") or "")
        item["ingestion_change"] = "recovered_pending_review"
        item["recovery_job_id"] = str(row["job_id"])
        out.append(item)
    return out
