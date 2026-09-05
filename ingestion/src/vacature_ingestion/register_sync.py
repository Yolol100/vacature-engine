from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

SCOPE = "https://www.googleapis.com/auth/spreadsheets"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _service_account_token(credentials: dict[str, Any]) -> str:
    email = str(credentials.get("client_email") or "").strip()
    private_key = str(credentials.get("private_key") or "")
    if not email or "BEGIN PRIVATE KEY" not in private_key:
        raise RuntimeError("service account JSON is missing client_email/private_key")
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps({
        "iss": email,
        "scope": SCOPE,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(private_key)
        key_path = handle.name
    try:
        signature = subprocess.check_output(
            ["openssl", "dgst", "-sha256", "-sign", key_path],
            input=signing_input,
        )
    finally:
        try:
            os.unlink(key_path)
        except OSError:
            pass
    assertion = f"{header}.{payload}.{_b64url(signature)}"
    body = urlencode({
        "grant_type": "urn:ietf:params:oauth-grant-type:jwt-bearer",
        "assertion": assertion,
    }).encode()
    request = Request(TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not token:
        raise RuntimeError("Google OAuth token response did not contain access_token")
    return str(token)


def _request_json(url: str, token: str, *, method: str = "GET", body: Any | None = None) -> Any:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")) if raw else {}


def _aggregate_health(
    health: dict[str, Any],
    *,
    allowed_instances: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for instance, value in health.items():
        instance = str(instance)
        if allowed_instances is not None and instance not in allowed_instances:
            continue
        if not isinstance(value, dict):
            continue
        source_id = instance.split(":", 1)[0]
        grouped.setdefault(source_id, []).append(value)
    out: dict[str, dict[str, Any]] = {}
    for source_id, rows in grouped.items():
        successes = sorted([str(row.get("last_success_at")) for row in rows if row.get("last_success_at")])
        failures = sorted([str(row.get("last_failure_at")) for row in rows if row.get("last_failure_at")])
        latest_failure_row = max(
            (row for row in rows if row.get("last_failure_at")),
            key=lambda row: str(row.get("last_failure_at")),
            default=None,
        )
        out[source_id] = {
            "last_success_at": successes[-1] if successes else None,
            "last_failure_at": failures[-1] if failures else None,
            "failure_category": latest_failure_row.get("failure_category") if latest_failure_row else None,
            "consecutive_failures": max((int(row.get("consecutive_failures") or 0) for row in rows), default=0),
            "next_retry_at": max((str(row.get("next_retry_at")) for row in rows if row.get("next_retry_at")), default=None),
            "last_result_count": sum(int(row.get("last_result_count") or 0) for row in rows if row.get("last_result_count") is not None),
        }
    return out


def sync_register(*, spreadsheet_id: str, summary_path: str | Path, health_path: str | Path) -> dict[str, Any]:
    raw_credentials = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw_credentials:
        return {"status": "skipped", "reason": "GOOGLE_SERVICE_ACCOUNT_JSON not configured"}
    credentials = json.loads(raw_credentials)
    token = _service_account_token(credentials)
    summary_doc = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    health_doc = json.loads(Path(health_path).read_text(encoding="utf-8"))
    runs = summary_doc.get("runs", []) if isinstance(summary_doc, dict) else []
    current_instances = {
        str(run.get("source_instance"))
        for run in runs
        if isinstance(run, dict) and run.get("source_instance")
    }
    health = health_doc.get("source_health", health_doc) if isinstance(health_doc, dict) else {}
    aggregated = _aggregate_health(
        health if isinstance(health, dict) else {},
        allowed_instances=current_instances,
    )

    base = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id)}"
    values_url = f"{base}/values/{quote('Bronnen!A1:O1000', safe='!')}"
    source_values = _request_json(values_url, token).get("values", [])
    row_by_source: dict[str, int] = {}
    for index, row in enumerate(source_values, start=1):
        if index == 1 or not row:
            continue
        row_by_source[str(row[0])] = index

    data: list[dict[str, Any]] = []
    for source_id, values in aggregated.items():
        row_num = row_by_source.get(source_id)
        if not row_num:
            continue
        data.append({
            "range": f"Bronnen!G{row_num}:L{row_num}",
            "values": [[
                values.get("last_success_at"),
                values.get("last_failure_at"),
                values.get("failure_category"),
                values.get("consecutive_failures", 0),
                values.get("next_retry_at"),
                values.get("last_result_count"),
            ]],
        })
    if data:
        _request_json(
            f"{base}/values:batchUpdate",
            token,
            method="POST",
            body={"valueInputOption": "RAW", "data": data},
        )

    now = datetime.now(timezone.utc).isoformat()
    started = str(summary_doc.get("started_at") or now)
    completed = str(summary_doc.get("completed_at") or now)
    checked = len(runs)
    normalized = sum(int(run.get("normalized") or 0) for run in runs)
    duplicates = sum(int(run.get("duplicate_observations") or run.get("duplicate_count") or 0) for run in runs)
    failures = [str(run.get("source_instance")) for run in runs if not run.get("success")]
    run_id = str(summary_doc.get("run_id") or f"ingestion-{int(time.time())}")
    review_queue_count = int(summary_doc.get("review_queue_count") or 0)
    notes = (
        f"Bulk ingestion: normalized={normalized}; new={sum(int(r.get('new') or 0) for r in runs)}; "
        f"updated={sum(int(r.get('updated') or 0) for r in runs)}; unchanged={sum(int(r.get('unchanged') or 0) for r in runs)}; "
        f"missing={sum(int(r.get('missing') or 0) for r in runs)}; closed={sum(int(r.get('closed') or 0) for r in runs)}; "
        f"review_queue_count={review_queue_count}; review_queue_processed=false. "
        "Raw technical state remains in GitHub ingestion-state; no candidate fit/scoring performed."
    )
    append_range = quote("Runs!A:M", safe="!")
    _request_json(
        f"{base}/values/{append_range}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
        token,
        method="POST",
        body={"values": [[
            run_id, started, completed, "bulk ingestion", checked, review_queue_count, 0, duplicates, 0, 0,
            ",".join(failures) if failures else "none", "success" if not failures else "partial", notes,
        ]]},
    )
    return {
        "status": "synced",
        "sources_updated": len(data),
        "run_id": run_id,
        "review_queue_count": review_queue_count,
    }
