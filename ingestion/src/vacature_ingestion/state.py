from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .normalize import strong_identity_keys


@dataclass
class UpsertCounts:
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicate_observations: int = 0
    missing: int = 0
    closed: int = 0


class StateStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.db.close()

    def _init_schema(self) -> None:
        self.db.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS jobs (
              job_id TEXT PRIMARY KEY,
              canonical_url TEXT,
              content_hash TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active',
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              closed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS identities (
              identity_key TEXT PRIMARY KEY,
              job_id TEXT NOT NULL REFERENCES jobs(job_id)
            );
            CREATE TABLE IF NOT EXISTS job_snapshots (
              job_id TEXT NOT NULL REFERENCES jobs(job_id),
              content_hash TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              PRIMARY KEY (job_id, content_hash)
            );
            CREATE TABLE IF NOT EXISTS source_membership (
              source_instance TEXT NOT NULL,
              job_id TEXT NOT NULL,
              missing_runs INTEGER NOT NULL DEFAULT 0,
              last_seen_run TEXT,
              close_threshold INTEGER NOT NULL DEFAULT 2,
              PRIMARY KEY (source_instance, job_id)
            );
            CREATE TABLE IF NOT EXISTS source_runs (
              run_id TEXT PRIMARY KEY,
              source_instance TEXT NOT NULL,
              started_at TEXT NOT NULL,
              finished_at TEXT,
              success INTEGER NOT NULL DEFAULT 0,
              fetched INTEGER NOT NULL DEFAULT 0,
              normalized INTEGER NOT NULL DEFAULT 0,
              new_count INTEGER NOT NULL DEFAULT 0,
              updated_count INTEGER NOT NULL DEFAULT 0,
              unchanged_count INTEGER NOT NULL DEFAULT 0,
              duplicate_count INTEGER NOT NULL DEFAULT 0,
              missing_count INTEGER NOT NULL DEFAULT 0,
              closed_count INTEGER NOT NULL DEFAULT 0,
              failure_category TEXT,
              failure_message TEXT
            );
            """
        )
        columns = {str(row[1]) for row in self.db.execute("PRAGMA table_info(source_membership)").fetchall()}
        if "close_threshold" not in columns:
            self.db.execute("ALTER TABLE source_membership ADD COLUMN close_threshold INTEGER NOT NULL DEFAULT 2")
        self.db.commit()

    def start_run(self, source_instance: str, started_at: str) -> str:
        run_id = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO source_runs(run_id, source_instance, started_at) VALUES (?, ?, ?)",
            (run_id, source_instance, started_at),
        )
        self.db.commit()
        return run_id

    def finish_run(self, run_id: str, *, success: bool, fetched: int, normalized: int,
                   counts: UpsertCounts | None = None, failure_category: str | None = None,
                   failure_message: str | None = None, finished_at: str | None = None) -> None:
        counts = counts or UpsertCounts()
        finished_at = finished_at or datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """UPDATE source_runs SET finished_at=?, success=?, fetched=?, normalized=?,
               new_count=?, updated_count=?, unchanged_count=?, duplicate_count=?,
               missing_count=?, closed_count=?, failure_category=?, failure_message=?
               WHERE run_id=?""",
            (finished_at, int(success), fetched, normalized, counts.new, counts.updated,
             counts.unchanged, counts.duplicate_observations, counts.missing, counts.closed,
             failure_category, failure_message, run_id),
        )
        self.db.commit()

    def _find_job_ids(self, keys: Iterable[str]) -> set[str]:
        keys = list(keys)
        if not keys:
            return set()
        placeholders = ",".join("?" for _ in keys)
        rows = self.db.execute(
            f"SELECT DISTINCT job_id FROM identities WHERE identity_key IN ({placeholders})", keys
        ).fetchall()
        return {row[0] for row in rows}

    def observation_change_state(self, row: dict[str, Any]) -> str:
        keys = strong_identity_keys(row)
        job_ids = self._find_job_ids(keys)
        if not job_ids:
            return "new"
        row_hash = str(row.get("content_hash") or "")
        placeholders = ",".join("?" for _ in job_ids)
        rows = self.db.execute(
            f"SELECT content_hash FROM jobs WHERE job_id IN ({placeholders})", list(job_ids)
        ).fetchall()
        if any(str(existing["content_hash"] or "") == row_hash for existing in rows):
            return "unchanged"
        return "updated"

    def _merge_jobs(self, target: str, source: str) -> None:
        if target == source:
            return
        target_row = self.db.execute("SELECT * FROM jobs WHERE job_id=?", (target,)).fetchone()
        source_row = self.db.execute("SELECT * FROM jobs WHERE job_id=?", (source,)).fetchone()
        if not target_row or not source_row:
            return
        first_seen = min(target_row["first_seen_at"], source_row["first_seen_at"])
        last_seen = max(target_row["last_seen_at"], source_row["last_seen_at"])
        self.db.execute("UPDATE jobs SET first_seen_at=?, last_seen_at=? WHERE job_id=?", (first_seen, last_seen, target))
        identity_rows = self.db.execute("SELECT identity_key FROM identities WHERE job_id=?", (source,)).fetchall()
        for identity_row in identity_rows:
            self.db.execute("INSERT OR REPLACE INTO identities(identity_key,job_id) VALUES (?,?)", (identity_row["identity_key"], target))
        self.db.execute("DELETE FROM identities WHERE job_id=?", (source,))

        snapshots = self.db.execute("SELECT * FROM job_snapshots WHERE job_id=?", (source,)).fetchall()
        for snapshot in snapshots:
            existing_snapshot = self.db.execute(
                "SELECT * FROM job_snapshots WHERE job_id=? AND content_hash=?",
                (target, snapshot["content_hash"]),
            ).fetchone()
            if existing_snapshot:
                snap_first = min(existing_snapshot["first_seen_at"], snapshot["first_seen_at"])
                snap_last = max(existing_snapshot["last_seen_at"], snapshot["last_seen_at"])
                self.db.execute(
                    "UPDATE job_snapshots SET first_seen_at=?,last_seen_at=? WHERE job_id=? AND content_hash=?",
                    (snap_first, snap_last, target, snapshot["content_hash"]),
                )
            else:
                self.db.execute(
                    "INSERT INTO job_snapshots(job_id,content_hash,payload_json,first_seen_at,last_seen_at) VALUES (?,?,?,?,?)",
                    (target, snapshot["content_hash"], snapshot["payload_json"], snapshot["first_seen_at"], snapshot["last_seen_at"]),
                )
        self.db.execute("DELETE FROM job_snapshots WHERE job_id=?", (source,))

        memberships = self.db.execute("SELECT * FROM source_membership WHERE job_id=?", (source,)).fetchall()
        for member in memberships:
            existing = self.db.execute(
                "SELECT * FROM source_membership WHERE source_instance=? AND job_id=?",
                (member["source_instance"], target),
            ).fetchone()
            if existing:
                missing = min(existing["missing_runs"], member["missing_runs"])
                last_run = max(existing["last_seen_run"] or "", member["last_seen_run"] or "") or None
                threshold = max(int(existing["close_threshold"] or 2), int(member["close_threshold"] or 2), 2)
                self.db.execute(
                    "UPDATE source_membership SET missing_runs=?, last_seen_run=?, close_threshold=? WHERE source_instance=? AND job_id=?",
                    (missing, last_run, threshold, member["source_instance"], target),
                )
            else:
                self.db.execute(
                    "INSERT INTO source_membership(source_instance,job_id,missing_runs,last_seen_run,close_threshold) VALUES (?,?,?,?,?)",
                    (member["source_instance"], target, member["missing_runs"], member["last_seen_run"], member["close_threshold"]),
                )
        self.db.execute("DELETE FROM source_membership WHERE job_id=?", (source,))
        self.db.execute("DELETE FROM jobs WHERE job_id=?", (source,))

    def _record_snapshot(self, job_id: str, row_hash: str, payload_json: str,
                         first_seen: str, last_seen: str) -> None:
        if not row_hash:
            return
        existing = self.db.execute(
            "SELECT first_seen_at,last_seen_at FROM job_snapshots WHERE job_id=? AND content_hash=?",
            (job_id, row_hash),
        ).fetchone()
        if existing:
            self.db.execute(
                "UPDATE job_snapshots SET first_seen_at=?,last_seen_at=? WHERE job_id=? AND content_hash=?",
                (min(existing["first_seen_at"], first_seen), max(existing["last_seen_at"], last_seen), job_id, row_hash),
            )
        else:
            self.db.execute(
                "INSERT INTO job_snapshots(job_id,content_hash,payload_json,first_seen_at,last_seen_at) VALUES (?,?,?,?,?)",
                (job_id, row_hash, payload_json, first_seen, last_seen),
            )

    def upsert_observations(self, observations: list[dict[str, Any]], *, source_instance: str,
                            run_id: str, missing_close_threshold: int = 2,
                            complete_snapshot: bool = True) -> UpsertCounts:
        counts = UpsertCounts()
        seen_jobs: set[str] = set()
        seen_strong_keys: set[str] = set()
        now = datetime.now(timezone.utc).isoformat()
        with self.db:
            for row in observations:
                keys = strong_identity_keys(row)
                if not keys:
                    continue
                if any(key in seen_strong_keys for key in keys):
                    counts.duplicate_observations += 1
                seen_strong_keys.update(keys)
                job_ids = self._find_job_ids(keys)
                if job_ids:
                    job_id = sorted(job_ids)[0]
                    for extra in sorted(job_ids - {job_id}):
                        self._merge_jobs(job_id, extra)
                    existing = self.db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
                else:
                    job_id = str(uuid.uuid4())
                    existing = None

                first_seen = str(row.get("first_seen_at") or now)
                last_seen = str(row.get("last_seen_at") or now)
                payload_json = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                row_hash = str(row.get("content_hash") or "")
                canonical_url = row.get("canonical_url")
                if existing is None:
                    self.db.execute(
                        "INSERT INTO jobs(job_id,canonical_url,content_hash,payload_json,status,first_seen_at,last_seen_at) VALUES (?,?,?,?,?,?,?)",
                        (job_id, canonical_url, row_hash, payload_json, "active", first_seen, last_seen),
                    )
                    counts.new += 1
                else:
                    if existing["content_hash"] != row_hash:
                        counts.updated += 1
                    else:
                        counts.unchanged += 1
                    self.db.execute(
                        "UPDATE jobs SET canonical_url=?,content_hash=?,payload_json=?,status='active',last_seen_at=?,closed_at=NULL WHERE job_id=?",
                        (canonical_url, row_hash, payload_json, last_seen, job_id),
                    )
                self._record_snapshot(job_id, row_hash, payload_json, first_seen, last_seen)
                for key in keys:
                    self.db.execute("INSERT OR REPLACE INTO identities(identity_key,job_id) VALUES (?,?)", (key, job_id))
                self.db.execute(
                    "INSERT INTO source_membership(source_instance,job_id,missing_runs,last_seen_run,close_threshold) VALUES (?,?,0,?,?) "
                    "ON CONFLICT(source_instance,job_id) DO UPDATE SET missing_runs=0,last_seen_run=excluded.last_seen_run,close_threshold=excluded.close_threshold",
                    (source_instance, job_id, run_id, max(2, int(missing_close_threshold))),
                )
                seen_jobs.add(job_id)

            if complete_snapshot:
                members = self.db.execute(
                    "SELECT source_instance,job_id,missing_runs,last_seen_run,close_threshold FROM source_membership WHERE source_instance=?",
                    (source_instance,),
                ).fetchall()
                for member in members:
                    job_id = member["job_id"]
                    if job_id in seen_jobs:
                        continue
                    next_missing = int(member["missing_runs"]) + 1
                    counts.missing += 1
                    self.db.execute(
                        "UPDATE source_membership SET missing_runs=? WHERE source_instance=? AND job_id=?",
                        (next_missing, source_instance, job_id),
                    )
                    if next_missing >= max(2, int(member["close_threshold"] or missing_close_threshold)):
                        memberships = self.db.execute(
                            "SELECT missing_runs,close_threshold FROM source_membership WHERE job_id=?",
                            (job_id,),
                        ).fetchall()
                        globally_missing = bool(memberships) and all(
                            int(item["missing_runs"] or 0) >= max(2, int(item["close_threshold"] or 2))
                            for item in memberships
                        )
                        if globally_missing:
                            existing_status = self.db.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
                            if existing_status and existing_status["status"] != "closed":
                                self.db.execute("UPDATE jobs SET status='closed',closed_at=? WHERE job_id=?", (now, job_id))
                                counts.closed += 1
        return counts

    def list_jobs(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM jobs ORDER BY first_seen_at, job_id").fetchall()
        return [dict(row) for row in rows]

    def snapshot_count(self) -> int:
        row = self.db.execute("SELECT COUNT(*) FROM job_snapshots").fetchone()
        return int(row[0] if row else 0)

    def snapshots_for_job(self, job_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM job_snapshots WHERE job_id=? ORDER BY first_seen_at,content_hash", (job_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def run_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute("SELECT * FROM source_runs ORDER BY started_at,run_id").fetchall()]

    def source_health(self, source_instance: str) -> dict[str, Any]:
        rows = [dict(row) for row in self.db.execute(
            "SELECT * FROM source_runs WHERE source_instance=? ORDER BY started_at,run_id",
            (source_instance,),
        ).fetchall()]
        successes = [row for row in rows if row["success"]]
        failures = [row for row in rows if not row["success"]]
        consecutive_failures = 0
        for row in reversed(rows):
            if row["success"]:
                break
            consecutive_failures += 1
        latest_failure = failures[-1] if failures else None
        next_retry_at = None
        if latest_failure and consecutive_failures:
            from datetime import datetime, timedelta
            raw = latest_failure.get("finished_at") or latest_failure.get("started_at")
            if raw:
                try:
                    base = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    delay = min(3600, 60 * (2 ** max(0, consecutive_failures - 1)))
                    next_retry_at = (base + timedelta(seconds=delay)).isoformat()
                except ValueError:
                    next_retry_at = None
        return {
            "source_instance": source_instance,
            "last_success_at": successes[-1]["finished_at"] if successes else None,
            "last_failure_at": latest_failure["finished_at"] if latest_failure else None,
            "failure_category": latest_failure["failure_category"] if latest_failure and consecutive_failures else None,
            "consecutive_failures": consecutive_failures,
            "next_retry_at": next_retry_at,
            "last_result_count": successes[-1]["normalized"] if successes else None,
            "run_count": len(rows),
        }

    def source_instances(self) -> list[str]:
        rows = self.db.execute("SELECT DISTINCT source_instance FROM source_runs ORDER BY source_instance").fetchall()
        return [str(row[0]) for row in rows]

    def export_state(self) -> dict[str, Any]:
        health = {instance: self.source_health(instance) for instance in self.source_instances()}
        return {
            "jobs": self.list_jobs(),
            "job_snapshot_count": self.snapshot_count(),
            "source_runs": self.run_rows(),
            "source_health": health,
        }
