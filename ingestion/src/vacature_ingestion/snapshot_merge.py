from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .review_queue import write_review_queue_pages


ACK_FALLBACK: dict[str, Any] = {
    "schema_version": 1,
    "acked_keys": [],
    "migrations": [],
}
QUEUE_FALLBACK: dict[str, Any] = {
    "schema_version": 1,
    "review_queue": [],
    "review_queue_count": 0,
}


def _load_object(path: str | Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return dict(fallback)
    return value if isinstance(value, dict) else dict(fallback)


def merge_ack_documents(remote: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    merged = dict(remote)
    for key, value in runtime.items():
        merged.setdefault(key, value)

    merged["schema_version"] = max(
        int(remote.get("schema_version") or 1),
        int(runtime.get("schema_version") or 1),
    )
    merged["acked_keys"] = sorted({
        str(value)
        for source in (remote.get("acked_keys", []), runtime.get("acked_keys", []))
        if isinstance(source, list)
        for value in source
        if value
    })
    merged["migrations"] = sorted({
        str(value)
        for source in (remote.get("migrations", []), runtime.get("migrations", []))
        if isinstance(source, list)
        for value in source
        if value
    })
    return merged


def merge_snapshot_files(*, state_dir: str | Path, runtime_dir: str | Path) -> dict[str, int]:
    state = Path(state_dir)
    runtime = Path(runtime_dir)

    remote_ack = _load_object(state / "review-ack.json", ACK_FALLBACK)
    runtime_ack = _load_object(runtime / "review-ack.json", ACK_FALLBACK)
    merged_ack = merge_ack_documents(remote_ack, runtime_ack)
    (state / "review-ack.json").write_text(
        json.dumps(merged_ack, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    queue = _load_object(runtime / "review-queue.json", QUEUE_FALLBACK)
    acked = set(merged_ack.get("acked_keys", []))
    raw_items = queue.get("review_queue", [])
    if not isinstance(raw_items, list):
        raw_items = []
    items = [
        item
        for item in raw_items
        if isinstance(item, dict) and str(item.get("review_key") or "") not in acked
    ]
    queue["review_queue"] = items
    queue["review_queue_count"] = len(items)
    queue.setdefault("schema_version", 1)
    (state / "review-queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_review_queue_pages(
        queue,
        directory=state / "review-queue-pages",
        index_path=state / "review-queue-index.json",
    )

    return {
        "acked_keys": len(merged_ack.get("acked_keys", [])),
        "migrations": len(merged_ack.get("migrations", [])),
        "pending_review": len(items),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge runtime review handoff into an ingestion-state worktree")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--runtime-dir", required=True)
    args = parser.parse_args(argv)
    result = merge_snapshot_files(state_dir=args.state_dir, runtime_dir=args.runtime_dir)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
