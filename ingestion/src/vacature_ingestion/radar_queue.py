from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_KEYS = {
    "ref", "source", "campaign", "gh_src", "li_fat_id", "mc_cid", "mc_eid", "referral",
}


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _canonical_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    query = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        low = key.casefold()
        if low.startswith("utm_") or low in _TRACKING_KEYS:
            continue
        query.append((key, val))
    return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), parts.path, urlencode(query), ""))


def radar_key(observation: dict[str, Any]) -> str:
    identity = "|".join(
        [
            str(observation.get("source_instance") or "").strip(),
            str(observation.get("source_job_id") or "").strip(),
            _canonical_url(observation.get("canonical_url") or observation.get("apply_url") or observation.get("url")),
        ]
    )
    return "radar:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _is_new_this_run(observation: dict[str, Any]) -> bool:
    first_seen = _dt(observation.get("first_seen_at"))
    ingested = _dt(observation.get("ingestion_timestamp"))
    if first_seen is None or ingested is None:
        return False
    return abs((first_seen - ingested).total_seconds()) <= 5


def _excerpt(value: Any, limit: int = 1200) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _compact_item(observation: dict[str, Any]) -> dict[str, Any]:
    url = _canonical_url(observation.get("canonical_url") or observation.get("apply_url") or observation.get("url"))
    return {
        "radar_key": radar_key(observation),
        "source_instance": observation.get("source_instance"),
        "source_id": observation.get("source_id"),
        "source_job_id": observation.get("source_job_id"),
        "source_type": observation.get("source_type"),
        "employer": observation.get("employer"),
        "title": observation.get("title"),
        "canonical_url": url,
        "apply_url": _canonical_url(observation.get("apply_url") or url),
        "first_seen_at": observation.get("first_seen_at"),
        "published_at": observation.get("published_at"),
        "updated_at": observation.get("updated_at"),
        "location": observation.get("location"),
        "listing_language": observation.get("listing_language"),
        "content_hash": observation.get("content_hash"),
        "description_excerpt": _excerpt(observation.get("description")),
    }


def _load_object(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists() or not p.read_text(encoding="utf-8").strip():
        return {}
    value = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{p} must contain a JSON object")
    return value


def build_first_seen_queue(
    current_doc: dict[str, Any],
    *,
    previous_doc: dict[str, Any] | None = None,
    ack_doc: dict[str, Any] | None = None,
    bootstrap: bool = False,
    ttl_hours: int = 72,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = now - timedelta(hours=max(1, int(ttl_hours)))
    acked = {str(v) for v in (ack_doc or {}).get("acked_keys", []) if v}

    pending: dict[str, dict[str, Any]] = {}
    previous_items = (previous_doc or {}).get("items", [])
    if isinstance(previous_items, list):
        for item in previous_items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("radar_key") or "")
            seen = _dt(item.get("first_seen_at"))
            if not key or key in acked or (seen is not None and seen < cutoff):
                continue
            pending[key] = dict(item)

    new_count = 0
    observations = current_doc.get("observations", [])
    if not bootstrap and isinstance(observations, list):
        for observation in observations:
            if not isinstance(observation, dict) or not _is_new_this_run(observation):
                continue
            item = _compact_item(observation)
            key = item["radar_key"]
            if key in acked or key in pending:
                continue
            seen = _dt(item.get("first_seen_at"))
            if seen is not None and seen < cutoff:
                continue
            pending[key] = item
            new_count += 1

    items = sorted(
        pending.values(),
        key=lambda item: (
            _dt(item.get("first_seen_at")) or datetime.max.replace(tzinfo=timezone.utc),
            str(item.get("radar_key") or ""),
        ),
    )
    return {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "source_run_id": current_doc.get("run_id"),
        "source_completed_at": current_doc.get("completed_at"),
        "bootstrap": bool(bootstrap),
        "ttl_hours": max(1, int(ttl_hours)),
        "new_item_count": new_count,
        "pending_count": len(items),
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a bounded first-seen vacancy radar queue")
    parser.add_argument("--current", required=True)
    parser.add_argument("--previous")
    parser.add_argument("--ack")
    parser.add_argument("--out", required=True)
    parser.add_argument("--ttl-hours", type=int, default=72)
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args()

    result = build_first_seen_queue(
        _load_object(args.current),
        previous_doc=_load_object(args.previous),
        ack_doc=_load_object(args.ack),
        bootstrap=args.bootstrap,
        ttl_hours=args.ttl_hours,
    )
    Path(args.out).write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "pending_count": result["pending_count"],
                "new_item_count": result["new_item_count"],
                "bootstrap": result["bootstrap"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
