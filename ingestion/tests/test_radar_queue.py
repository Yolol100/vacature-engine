from __future__ import annotations

import unittest
from datetime import datetime, timezone

from vacature_ingestion.radar_queue import build_first_seen_queue, radar_key


NOW = datetime(2026, 9, 5, 21, 0, tzinfo=timezone.utc)


def observation(
    job_id: str = "1",
    *,
    first_seen: str = "2026-09-05T21:00:00+00:00",
    ingested: str = "2026-09-05T21:00:00+00:00",
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
        "description": "WordPress WooCommerce " * 100,
    }


class RadarQueueTests(unittest.TestCase):
    def test_bootstrap_does_not_flood_existing_jobs(self) -> None:
        result = build_first_seen_queue({"observations": [observation()]}, bootstrap=True, now=NOW)
        self.assertEqual(0, result["pending_count"])
        self.assertEqual(0, result["new_item_count"])

    def test_new_observation_is_queued_and_tracking_removed(self) -> None:
        result = build_first_seen_queue({"run_id": "r1", "observations": [observation()]}, now=NOW)
        self.assertEqual(1, result["pending_count"])
        self.assertEqual(1, result["new_item_count"])
        self.assertEqual("https://jobs.example.com/1", result["items"][0]["canonical_url"])
        self.assertLessEqual(len(result["items"][0]["description_excerpt"]), 1200)

    def test_old_observation_seen_again_is_not_new(self) -> None:
        result = build_first_seen_queue(
            {"observations": [observation(first_seen="2026-09-05T20:00:00+00:00")]},
            now=NOW,
        )
        self.assertEqual(0, result["pending_count"])

    def test_previous_pending_survives_and_deduplicates(self) -> None:
        item = build_first_seen_queue({"observations": [observation()]}, now=NOW)["items"][0]
        result = build_first_seen_queue(
            {"observations": [observation()]},
            previous_doc={"items": [item]},
            now=NOW,
        )
        self.assertEqual(1, result["pending_count"])
        self.assertEqual(0, result["new_item_count"])

    def test_ack_removes_item(self) -> None:
        item = build_first_seen_queue({"observations": [observation()]}, now=NOW)["items"][0]
        result = build_first_seen_queue(
            {"observations": []},
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
            {"observations": [old]}, ttl_hours=200, now=NOW
        )["items"][0]
        result = build_first_seen_queue(
            {"observations": []},
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


if __name__ == "__main__":
    unittest.main()
