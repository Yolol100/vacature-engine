from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from vacature_ingestion.models import SourceSpec
from vacature_ingestion.radar_queue import build_first_seen_queue, radar_key
from vacature_ingestion.runner import IngestionRunner


NOW = datetime(2026, 9, 5, 21, 0, tzinfo=timezone.utc)


def observation(
    job_id: str = "1",
    *,
    first_seen: str = "2026-09-05T21:00:00+00:00",
    ingested: str = "2026-09-05T21:00:00+00:00",
    change: str = "new",
) -> dict[str, object]:
    return {
        "source_instance": "greenhouse:example",
        "source_id": "greenhouse",
        "source_job_id": f"example:{job_id}",
        "source_type": "ats",
        "employer": "Example",
        "title": "WordPress Developer",
        "canonical_url": f"https://jobs.example.com/{job_id}?utm_source=x&ref=y",
        "apply_url": f"https://jobs.example.com/{job_id}",
        "first_seen_at": first_seen,
        "ingestion_timestamp": ingested,
        "ingestion_change": change,
        "description": "WordPress WooCommerce " * 100,
    }


def current_doc(*items: dict[str, object], run_id: str = "r1") -> dict[str, object]:
    return {"run_id": run_id, "review_queue": list(items), "observations": list(items)}


class RadarQueueTests(unittest.TestCase):
    def test_bootstrap_does_not_flood_existing_jobs(self) -> None:
        result = build_first_seen_queue(current_doc(observation()), bootstrap=True, now=NOW)
        self.assertEqual(0, result["pending_count"])
        self.assertEqual(0, result["new_item_count"])

    def test_new_observation_is_queued_and_tracking_removed(self) -> None:
        result = build_first_seen_queue(current_doc(observation()), now=NOW)
        self.assertEqual(1, result["pending_count"])
        self.assertEqual(1, result["new_item_count"])
        self.assertEqual("https://jobs.example.com/1", result["items"][0]["canonical_url"])
        self.assertLessEqual(len(result["items"][0]["description_excerpt"]), 1200)

    def test_updated_observation_is_not_first_seen(self) -> None:
        result = build_first_seen_queue(current_doc(observation(change="updated")), now=NOW)
        self.assertEqual(0, result["pending_count"])
        self.assertEqual(0, result["new_item_count"])

    def test_missing_state_change_fails_closed(self) -> None:
        item = observation()
        item.pop("ingestion_change")
        result = build_first_seen_queue(
            {"observations": [item]},
            now=NOW,
        )
        self.assertEqual(0, result["pending_count"])
        self.assertEqual(0, result["new_item_count"])

    def test_previous_pending_survives_and_deduplicates(self) -> None:
        item = build_first_seen_queue(current_doc(observation()), now=NOW)["items"][0]
        result = build_first_seen_queue(
            current_doc(observation()),
            previous_doc={"items": [item]},
            now=NOW,
        )
        self.assertEqual(1, result["pending_count"])
        self.assertEqual(0, result["new_item_count"])

    def test_ack_removes_item(self) -> None:
        item = build_first_seen_queue(current_doc(observation()), now=NOW)["items"][0]
        result = build_first_seen_queue(
            current_doc(),
            previous_doc={"items": [item]},
            ack_doc={"acked_keys": [item["radar_key"]]},
            now=NOW,
        )
        self.assertEqual(0, result["pending_count"])

    def test_expired_pending_item_is_dropped(self) -> None:
        old = observation(
            first_seen="2026-09-01T00:00:00+00:00",
            ingested="2026-09-01T00:00:00+00:00",
        )
        item = build_first_seen_queue(
            current_doc(old), ttl_hours=200, now=NOW
        )["items"][0]
        result = build_first_seen_queue(
            current_doc(),
            previous_doc={"items": [item]},
            ttl_hours=72,
            now=NOW,
        )
        self.assertEqual(0, result["pending_count"])

    def test_key_is_stable_across_tracking_params(self) -> None:
        first = observation()
        second = observation()
        second["canonical_url"] = "https://jobs.example.com/1?utm_campaign=abc"
        self.assertEqual(radar_key(first), radar_key(second))

    def test_stateful_bootstrap_repeat_then_new_job(self) -> None:
        first = {
            "id": 1,
            "title": "WordPress Developer",
            "absolute_url": "https://jobs.example.com/1",
            "content": "WordPress WooCommerce",
            "location": {"name": "Remote"},
        }
        second = {
            "id": 2,
            "title": "WordPress Support Engineer",
            "absolute_url": "https://jobs.example.com/2",
            "content": "WordPress support debugging",
            "location": {"name": "Remote"},
        }
        spec = SourceSpec("greenhouse", "ats", "greenhouse", "example", employer="Example")
        with tempfile.TemporaryDirectory() as td:
            runner = IngestionRunner(Path(td) / "state.sqlite3")
            try:
                r1 = runner.ingest_records(spec, [first], now="2026-09-05T21:00:00+00:00")
                q1 = build_first_seen_queue(
                    {"run_id": "r1", "review_queue": r1.review_observations or []},
                    bootstrap=True,
                    now=NOW,
                )
                self.assertEqual(0, q1["pending_count"])

                r2 = runner.ingest_records(spec, [first], now="2026-09-05T21:05:00+00:00")
                self.assertEqual([], r2.review_observations)
                q2 = build_first_seen_queue(
                    {"run_id": "r2", "review_queue": r2.review_observations or []},
                    previous_doc=q1,
                    now=datetime(2026, 9, 5, 21, 5, tzinfo=timezone.utc),
                )
                self.assertEqual(0, q2["pending_count"])
                self.assertEqual(0, q2["new_item_count"])

                r3 = runner.ingest_records(spec, [first, second], now="2026-09-05T21:10:00+00:00")
                self.assertEqual(["new"], [item["ingestion_change"] for item in r3.review_observations or []])
                q3 = build_first_seen_queue(
                    {"run_id": "r3", "review_queue": r3.review_observations or []},
                    previous_doc=q2,
                    now=datetime(2026, 9, 5, 21, 10, tzinfo=timezone.utc),
                )
                self.assertEqual(1, q3["pending_count"])
                self.assertEqual(1, q3["new_item_count"])
                self.assertEqual("example:2", q3["items"][0]["source_job_id"])
            finally:
                runner.close()


if __name__ == "__main__":
    unittest.main()
