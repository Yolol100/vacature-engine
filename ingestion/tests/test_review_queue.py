from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vacature_ingestion.review_queue import (
    DESCRIPTION_EXCERPT_CHARS,
    build_review_queue,
    review_key,
    write_review_queue_pages,
)


class ReviewQueueTests(unittest.TestCase):
    def _job(self, job_id: str, content_hash: str) -> dict[str, str]:
        return {
            "source_id": "greenhouse",
            "source_job_id": job_id,
            "canonical_url": f"https://example.test/jobs/{job_id}",
            "content_hash": content_hash,
            "title": f"Job {job_id}",
        }

    def test_previous_pending_items_survive_next_ingestion(self):
        old = self._job("1", "aaa")
        previous = {"run_id": "old", "completed_at": "2026-09-05T10:00:00Z", "review_queue": [old]}
        current = {"run_id": "new", "completed_at": "2026-09-05T11:00:00Z", "review_queue": []}
        result = build_review_queue(current, previous_doc=previous)
        self.assertEqual(result["review_queue_count"], 1)
        self.assertEqual(result["review_queue"][0]["origin_run_id"], "old")

    def test_acknowledged_item_is_pruned(self):
        item = self._job("1", "aaa")
        previous = {"run_id": "old", "completed_at": "2026-09-05T10:00:00Z", "review_queue": [item]}
        current = {"run_id": "new", "completed_at": "2026-09-05T11:00:00Z", "review_queue": []}
        ack = {"acked_keys": [review_key(item)]}
        result = build_review_queue(current, previous_doc=previous, ack_doc=ack)
        self.assertEqual(result["review_queue_count"], 0)

    def test_content_change_gets_new_review_key(self):
        first = self._job("1", "aaa")
        changed = self._job("1", "bbb")
        self.assertNotEqual(review_key(first), review_key(changed))

    def test_current_item_replaces_same_pending_key(self):
        item = self._job("1", "aaa")
        previous = {"run_id": "old", "completed_at": "2026-09-05T10:00:00Z", "review_queue": [item]}
        current = {"run_id": "new", "completed_at": "2026-09-05T11:00:00Z", "review_queue": [item]}
        result = build_review_queue(current, previous_doc=previous)
        self.assertEqual(result["review_queue_count"], 1)
        self.assertTrue(result["review_queue"][0]["queue_seen_in_current_run"])

    def test_large_description_is_compacted(self):
        item = self._job("1", "aaa")
        item["description"] = "<p>" + ("WordPress developer work " * 200) + "</p>"
        current = {"run_id": "new", "completed_at": "2026-09-05T11:00:00Z", "review_queue": [item]}
        result = build_review_queue(current)
        queued = result["review_queue"][0]
        self.assertNotIn("description", queued)
        self.assertLessEqual(len(queued["description_excerpt"]), DESCRIPTION_EXCERPT_CHARS)
        self.assertIn("WordPress developer work", queued["description_excerpt"])

    def test_existing_review_key_survives_compaction(self):
        item = self._job("1", "aaa")
        item["review_key"] = "review:precomputed"
        previous = {"run_id": "old", "completed_at": "2026-09-05T10:00:00Z", "review_queue": [item]}
        result = build_review_queue(
            {"run_id": "new", "completed_at": "2026-09-05T11:00:00Z", "review_queue": []},
            previous_doc=previous,
        )
        self.assertEqual(result["review_queue"][0]["review_key"], "review:precomputed")

    def test_paginated_handoff_is_bounded_and_indexed(self):
        queue = {
            "run_id": "run-1",
            "completed_at": "2026-09-05T11:00:00Z",
            "review_queue": [
                {**self._job(str(i), f"hash-{i}"), "review_key": f"review:{i:03d}"}
                for i in range(53)
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            index = write_review_queue_pages(
                queue,
                directory=root / "review-queue-pages",
                index_path=root / "review-queue-index.json",
                page_size=25,
            )
            self.assertEqual(index["review_queue_count"], 53)
            self.assertEqual(index["total_pages"], 3)
            self.assertEqual([page["count"] for page in index["pages"]], [25, 25, 3])
            first = json.loads((root / "review-queue-pages" / "page-0001.json").read_text(encoding="utf-8"))
            last = json.loads((root / "review-queue-pages" / "page-0003.json").read_text(encoding="utf-8"))
            self.assertEqual(first["page_item_count"], 25)
            self.assertEqual(last["page_item_count"], 3)
            self.assertEqual(index["pages"][0]["path"], "review-queue-pages/page-0001.json")

    def test_paginated_handoff_removes_stale_pages(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pages = root / "review-queue-pages"
            pages.mkdir()
            (pages / "page-9999.json").write_text("{}", encoding="utf-8")
            write_review_queue_pages(
                {"run_id": "run-1", "review_queue": []},
                directory=pages,
                index_path=root / "review-queue-index.json",
            )
            self.assertFalse((pages / "page-9999.json").exists())
            index = json.loads((root / "review-queue-index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["total_pages"], 0)


if __name__ == "__main__":
    unittest.main()
