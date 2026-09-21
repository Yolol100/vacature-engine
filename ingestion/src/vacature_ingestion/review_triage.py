from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .register_sync import _request_json, _service_account_token
from .review_queue import write_review_queue_pages
from .workflow_state import normalize_ack_document


class ReviewTriagePolicyError(RuntimeError):
    pass


def _split_csv(value: Any) -> list[str]:
    if value is None:
        return []
    return sorted({
        part.strip().casefold()
        for part in str(value).split(",")
        if part.strip()
    })


def policy_from_config_values(values: Any) -> dict[str, Any]:
    if not isinstance(values, list) or not values:
        raise ReviewTriagePolicyError("Config sheet returned no rows")

    config: dict[str, str] = {}
    for row in values[1:]:
        if not isinstance(row, list) or not row:
            continue
        key = str(row[0] or "").strip()
        if not key:
            continue
        config[key] = str(row[1] if len(row) > 1 else "").strip()

    enabled = config.get("ingestion_review_auto_ack_nonpriority", "").strip().upper() == "TRUE"
    terms = _split_csv(config.get("ingestion_review_priority_terms"))
    employers = _split_csv(config.get("ingestion_review_priority_employers"))
    policy_version = config.get("ingestion_review_triage_policy_version", "").strip()

    if enabled and not (terms or employers):
        raise ReviewTriagePolicyError(
            "ingestion review triage is enabled but no priority terms or employers are configured"
        )

    return {
        "enabled": enabled,
        "terms": terms,
        "employers": employers,
        "policy_version": policy_version or "unversioned",
    }


def read_review_triage_policy(spreadsheet_id: str) -> dict[str, Any]:
    raw_credentials = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw_credentials:
        raise ReviewTriagePolicyError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is required for Config-owned review triage"
        )
    credentials = json.loads(raw_credentials)
    token = _service_account_token(credentials)
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id)}"
    range_ref = quote("Config!A1:F1000", safe="!")
    response = _request_json(f"{base}/values/{range_ref}", token)
    values = response.get("values", []) if isinstance(response, dict) else []
    return policy_from_config_values(values)


def _text_blob(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in (
        "title",
        "employer",
        "description_excerpt",
        "location",
        "workplace_type",
        "employment_type",
    ):
        value = item.get(field)
        if value:
            parts.append(str(value))

    for field in ("tags", "keywords"):
        value = item.get(field)
        if isinstance(value, list):
            parts.extend(str(part) for part in value if part)
        elif value:
            parts.append(str(value))

    metadata = item.get("source_metadata")
    if isinstance(metadata, dict):
        parts.append(json.dumps(metadata, ensure_ascii=False, sort_keys=True))
    elif metadata:
        parts.append(str(metadata))

    return " ".join(parts).casefold()


def priority_reason(item: dict[str, Any], policy: dict[str, Any]) -> str | None:
    employer = str(item.get("employer") or "").strip().casefold()
    for configured in policy.get("employers", []):
        if configured and configured in employer:
            return f"employer:{configured}"

    blob = _text_blob(item)
    for term in policy.get("terms", []):
        if term and term in blob:
            return f"term:{term}"
    return None


def _identity_key(item: dict[str, Any]) -> str:
    source_id = str(item.get("source_id") or "").strip()
    source_job_id = str(item.get("source_job_id") or "").strip()
    if source_id and source_job_id:
        return f"source:{source_id}:{source_job_id}"
    for field in ("canonical_url", "url", "source_url"):
        value = str(item.get(field) or "").strip()
        if value:
            return f"url:{value}"
    return f"review:{str(item.get('review_key') or '').strip()}"


def _latest_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, item in enumerate(items):
        grouped.setdefault(_identity_key(item), []).append((index, item))

    latest: list[dict[str, Any]] = []
    superseded: list[dict[str, Any]] = []
    for group in grouped.values():
        ordered = sorted(
            group,
            key=lambda pair: (
                str(pair[1].get("origin_completed_at") or ""),
                pair[0],
            ),
        )
        latest.append(ordered[-1][1])
        superseded.extend(item for _, item in ordered[:-1])
    return latest, superseded


def triage_review_queue(
    queue_doc: dict[str, Any],
    ack_doc: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    queue = dict(queue_doc) if isinstance(queue_doc, dict) else {}
    ack = normalize_ack_document(ack_doc)
    raw_items = queue.get("review_queue", [])
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []

    if not policy.get("enabled"):
        queue["review_queue"] = items
        queue["review_queue_count"] = len(items)
        return queue, ack, {
            "schema_version": 1,
            "policy_version": policy.get("policy_version", "unversioned"),
            "enabled": False,
            "input_count": len(items),
            "priority_pending": len(items),
            "auto_acked_nonpriority": 0,
            "missing_review_key": sum(1 for item in items if not item.get("review_key")),
            "normal_discovery_fallback_required": True,
        }

    pending: list[dict[str, Any]] = []
    auto_acked: list[str] = []
    superseded_acked: list[str] = []
    missing_key = 0
    reason_counts: dict[str, int] = {}

    latest_items, superseded_items = _latest_items(items)
    for item in superseded_items:
        key = str(item.get("review_key") or "").strip()
        if key:
            superseded_acked.append(key)
        else:
            missing_key += 1
            pending.append(item)

    for item in latest_items:
        key = str(item.get("review_key") or "").strip()
        if not key:
            missing_key += 1
            pending.append(item)
            continue

        reason = priority_reason(item, policy)
        if reason:
            pending.append(item)
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            continue

        auto_acked.append(key)

    ack["acked_keys"] = sorted(
        set(ack.get("acked_keys", [])) | set(auto_acked) | set(superseded_acked)
    )
    queue["review_queue"] = pending
    queue["review_queue_count"] = len(pending)
    queue.setdefault("schema_version", 1)

    report = {
        "schema_version": 1,
        "policy_version": policy.get("policy_version", "unversioned"),
        "enabled": True,
        "input_count": len(items),
        "priority_pending": len(pending),
        "auto_acked_nonpriority": len(auto_acked),
        "superseded_versions_acked": len(superseded_acked),
        "missing_review_key": missing_key,
        "priority_reason_counts": dict(sorted(reason_counts.items())),
        "normal_discovery_fallback_required": True,
        "decision_boundary": (
            "technical priority-hint triage only; no authenticity, eligibility, fit, score, "
            "source-priority or application decision is made here"
        ),
    }
    return queue, ack, report


def _load_object(path: str | Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return dict(default)
    return value if isinstance(value, dict) else dict(default)


def _write_object(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def apply_review_triage(
    *,
    queue_path: str | Path,
    ack_path: str | Path,
    spreadsheet_id: str,
    report_path: str | Path,
    pages_dir: str | Path,
    index_path: str | Path,
) -> dict[str, Any]:
    queue = _load_object(queue_path, {"schema_version": 1, "review_queue": [], "review_queue_count": 0})
    ack = _load_object(ack_path, {"schema_version": 1, "acked_keys": [], "migrations": []})
    policy = read_review_triage_policy(spreadsheet_id)
    filtered, updated_ack, report = triage_review_queue(queue, ack, policy)

    _write_object(queue_path, filtered)
    _write_object(ack_path, updated_ack)
    _write_object(report_path, report)
    index = write_review_queue_pages(filtered, directory=pages_dir, index_path=index_path)
    report["output_pages"] = int(index.get("total_pages") or 0)
    report["oldest_priority_pending_at"] = index.get("oldest_origin_completed_at")
    _write_object(report_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Triage ingestion review handoff using live Config-owned priority hints"
    )
    parser.add_argument("--queue", required=True)
    parser.add_argument("--ack", required=True)
    parser.add_argument("--spreadsheet-id", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--pages-dir", required=True)
    parser.add_argument("--index-out", required=True)
    args = parser.parse_args(argv)

    result = apply_review_triage(
        queue_path=args.queue,
        ack_path=args.ack,
        spreadsheet_id=args.spreadsheet_id,
        report_path=args.report,
        pages_dir=args.pages_dir,
        index_path=args.index_out,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
