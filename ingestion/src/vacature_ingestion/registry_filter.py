from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote

from .register_sync import _request_json, _service_account_token


class RegistrySourceError(RuntimeError):
    pass


def active_source_rows_from_values(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list) or not values:
        raise RegistrySourceError("Bronnen sheet returned no rows")
    header = values[0]
    if not isinstance(header, list):
        raise RegistrySourceError("Bronnen header is invalid")
    columns = {str(value).strip(): index for index, value in enumerate(header)}
    required = {"source_id", "status"}
    if not required.issubset(columns):
        raise RegistrySourceError("Bronnen must contain source_id and status columns")

    rows: list[dict[str, str]] = []
    for raw_row in values[1:]:
        if not isinstance(raw_row, list):
            continue
        source_col = columns["source_id"]
        status_col = columns["status"]
        if source_col >= len(raw_row):
            continue
        source_id = str(raw_row[source_col] or "").strip()
        status = str(raw_row[status_col] if status_col < len(raw_row) else "").strip().lower()
        if not source_id or status != "active":
            continue
        row: dict[str, str] = {}
        for name, index in columns.items():
            row[name] = str(raw_row[index] if index < len(raw_row) else "").strip()
        rows.append(row)
    if not rows:
        raise RegistrySourceError("Bronnen contains no active sources")
    return rows


def active_source_ids_from_values(values: Any) -> set[str]:
    return {row["source_id"] for row in active_source_rows_from_values(values)}


def _read_source_values(spreadsheet_id: str) -> list[list[Any]]:
    raw_credentials = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw_credentials:
        raise RegistrySourceError("GOOGLE_SERVICE_ACCOUNT_JSON is required for Register-owned source gating")
    credentials = json.loads(raw_credentials)
    token = _service_account_token(credentials)
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id)}"
    range_ref = quote("Bronnen!A1:O2000", safe="!")
    response = _request_json(f"{base}/values/{range_ref}", token)
    values = response.get("values", []) if isinstance(response, dict) else []
    return values if isinstance(values, list) else []


def read_active_source_rows(spreadsheet_id: str) -> list[dict[str, str]]:
    return active_source_rows_from_values(_read_source_values(spreadsheet_id))


def read_active_source_ids(spreadsheet_id: str) -> set[str]:
    return {row["source_id"] for row in read_active_source_rows(spreadsheet_id)}


def required_registry_ids(spec: dict[str, Any]) -> set[str]:
    required = {str(spec.get("source_id") or "").strip()}
    options = spec.get("options")
    if isinstance(options, dict):
        extra = options.get("registry_source_id")
        if isinstance(extra, str) and extra.strip():
            required.add(extra.strip())
        elif isinstance(extra, list):
            required.update(str(value).strip() for value in extra if str(value).strip())
    return {value for value in required if value}


def filter_source_specs(
    specs: list[dict[str, Any]], active_source_ids: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        required = required_registry_ids(spec)
        missing = sorted(required - active_source_ids)
        if missing:
            blocked.append({
                "source_instance": f"{spec.get('source_id')}:{spec.get('account')}",
                "missing_active_registry_ids": missing,
            })
        else:
            accepted.append(spec)
    return accepted, blocked
