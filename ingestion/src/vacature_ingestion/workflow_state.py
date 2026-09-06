from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ACK = {"schema_version": 1, "acked_keys": [], "migrations": []}


def _load_object(path: str | Path, default: dict[str, Any] | None = None) -> dict[str, Any] | None:
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
        if not text.strip():
            return dict(default) if default is not None else None
        value = json.loads(text)
    except (OSError, ValueError, json.JSONDecodeError):
        return dict(default) if default is not None else None
    return value if isinstance(value, dict) else (dict(default) if default is not None else None)


def _write_object(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_ack_document(value: object) -> dict[str, Any]:
    document = dict(value) if isinstance(value, dict) else {}
    try:
        schema_version = max(1, int(document.get("schema_version", 1)))
    except (TypeError, ValueError):
        schema_version = 1
    document["schema_version"] = schema_version
    document["acked_keys"] = sorted({str(item) for item in document.get("acked_keys", []) if item})
    document["migrations"] = sorted({str(item) for item in document.get("migrations", []) if item})
    return document


def normalize_ack_file(path: str | Path) -> dict[str, Any]:
    document = normalize_ack_document(_load_object(path, DEFAULT_ACK))
    _write_object(path, document)
    return document


def merge_ack_documents(local: object, remote: object) -> dict[str, Any]:
    local_doc = normalize_ack_document(local)
    remote_doc = normalize_ack_document(remote)
    merged = dict(remote_doc)
    for key, value in local_doc.items():
        if key not in {"schema_version", "acked_keys", "migrations"} and key not in merged:
            merged[key] = value
    merged["schema_version"] = max(local_doc["schema_version"], remote_doc["schema_version"])
    merged["acked_keys"] = sorted(set(local_doc["acked_keys"]) | set(remote_doc["acked_keys"]))
    merged["migrations"] = sorted(set(local_doc["migrations"]) | set(remote_doc["migrations"]))
    return merged


def cmd_normalize_ack(args: argparse.Namespace) -> int:
    document = normalize_ack_file(args.path)
    print(json.dumps({"acked": len(document["acked_keys"]), "migrations": len(document["migrations"])}, sort_keys=True))
    return 0


def cmd_merge_ack(args: argparse.Namespace) -> int:
    local = _load_object(args.local, DEFAULT_ACK)
    remote = _load_object(args.remote, DEFAULT_ACK)
    merged = merge_ack_documents(local, remote)
    _write_object(args.local, merged)
    print(json.dumps({"acked": len(merged["acked_keys"]), "migrations": len(merged["migrations"])}, sort_keys=True))
    return 0


def cmd_recover_review(args: argparse.Namespace) -> int:
    from .review_backlog import load_review_backlog

    request_path = Path(args.request)
    recovery_path = Path(args.out)
    _write_object(recovery_path, {})
    if not request_path.exists():
        print(json.dumps({"recovery": "not_requested"}, sort_keys=True))
        return 0

    request = _load_object(request_path)
    if request is None:
        raise SystemExit("review backlog recovery request must be a JSON object")
    ack = normalize_ack_file(args.ack)
    migration_id = str(request.get("migration_id") or "").strip()
    since = str(request.get("since") or "").strip()
    origin_run_id = str(request.get("origin_run_id") or f"recovery:{migration_id}")
    if not migration_id or not since:
        raise SystemExit("review backlog recovery request requires migration_id and since")
    if migration_id in ack["migrations"]:
        print(json.dumps({"recovery": "already_applied", "migration_id": migration_id}, sort_keys=True))
        return 0

    rows = load_review_backlog(args.state, since=since, active_only=True)
    recovery = {
        "run_id": origin_run_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "review_queue_count": len(rows),
        "review_queue": rows,
    }
    _write_object(recovery_path, recovery)
    ack["migrations"] = sorted(set(ack["migrations"]) | {migration_id})
    _write_object(args.ack, ack)
    print(json.dumps({"recovery": "prepared", "migration_id": migration_id, "recovered": len(rows)}, sort_keys=True))
    return 0


def cmd_build_review_queue(args: argparse.Namespace) -> int:
    from .review_queue import build_review_queue, write_review_queue_pages

    current = _load_object(args.current) or {}
    previous = _load_object(args.previous)
    recovery = _load_object(args.recovery)
    ack = _load_object(args.ack)
    seed = previous
    if recovery and isinstance(recovery.get("review_queue"), list):
        seed = build_review_queue(recovery, previous_doc=seed, ack_doc=ack)
    compact = build_review_queue(current, previous_doc=seed, ack_doc=ack)
    _write_object(args.out, compact)
    index = write_review_queue_pages(compact, directory=args.pages_dir, index_path=args.index_out)
    print(json.dumps({
        "run_id": compact.get("run_id"),
        "review_queue_count": compact.get("review_queue_count", 0),
        "review_queue_pages": index.get("total_pages", 0),
        "oldest_pending_at": index.get("oldest_origin_completed_at"),
    }, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m vacature_ingestion.workflow_state")
    sub = parser.add_subparsers(dest="command", required=True)

    normalize = sub.add_parser("normalize-ack")
    normalize.add_argument("--path", required=True)
    normalize.set_defaults(func=cmd_normalize_ack)

    merge = sub.add_parser("merge-ack")
    merge.add_argument("--local", required=True)
    merge.add_argument("--remote", required=True)
    merge.set_defaults(func=cmd_merge_ack)

    recover = sub.add_parser("recover-review")
    recover.add_argument("--request", required=True)
    recover.add_argument("--ack", required=True)
    recover.add_argument("--state", required=True)
    recover.add_argument("--out", required=True)
    recover.set_defaults(func=cmd_recover_review)

    queue = sub.add_parser("build-review-queue")
    queue.add_argument("--current", required=True)
    queue.add_argument("--previous", required=True)
    queue.add_argument("--recovery", required=True)
    queue.add_argument("--ack", required=True)
    queue.add_argument("--out", required=True)
    queue.add_argument("--pages-dir", required=True)
    queue.add_argument("--index-out", required=True)
    queue.set_defaults(func=cmd_build_review_queue)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
