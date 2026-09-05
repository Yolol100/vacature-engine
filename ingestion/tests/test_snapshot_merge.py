from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vacature_ingestion.snapshot_merge import merge_ack_documents, merge_snapshot_files


class SnapshotMergeTests(unittest.TestCase):
    def test_ack_merge_preserves_remote_and_runtime_keys_and_unknown_fields(self):
        remote = {
            "schema_version": 1,
            "acked_keys": ["review:a"],
            "migrations": ["old"],
            "remote_only": "keep",
        }
        runtime = {
            "schema_version": 2,
            "acked_keys": ["review:b", "review:a"],
            "migrations": ["new"],
            "runtime_only": "keep-too",
        }
        merged = merge_ack_documents(remote, runtime)
        self.assertEqual(merged["schema_version"], 2)
        self.assertEqual(merged["acked_keys"], ["review:a", "review:b"])
        self.assertEqual(merged["migrations"], ["new", "old"])
        self.assertEqual(merged["remote_only"], "keep")
        self.assertEqual(merged["runtime_only"], "keep-too")

    def test_snapshot_prunes_acknowledged_queue_items(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / "state"
            runtime = root / "runtime"
            state.mkdir()
            runtime.mkdir()
            (state / "review-ack.json").write_text(
                json.dumps({"schema_version": 1, "acked_keys": ["review:a"], "migrations": []}),
                encoding="utf-8",
            )
            (runtime / "review-ack.json").write_text(
                json.dumps({"schema_version": 1, "acked_keys": ["review:b"], "migrations": ["recovery"]}),
                encoding="utf-8",
            )
            (runtime / "review-queue.json").write_text(
                json.dumps({
                    "schema_version": 1,
                    "run_id": "run-1",
                    "review_queue": [
                        {"review_key": "review:a", "title": "A"},
                        {"review_key": "review:b", "title": "B"},
                        {"review_key": "review:c", "title": "C"},
                    ],
                }),
                encoding="utf-8",
            )

            result = merge_snapshot_files(state_dir=state, runtime_dir=runtime)
            self.assertEqual(result, {"acked_keys": 2, "migrations": 1, "pending_review": 1})

            ack = json.loads((state / "review-ack.json").read_text(encoding="utf-8"))
            queue = json.loads((state / "review-queue.json").read_text(encoding="utf-8"))
            self.assertEqual(ack["acked_keys"], ["review:a", "review:b"])
            self.assertEqual(ack["migrations"], ["recovery"])
            self.assertEqual(queue["review_queue_count"], 1)
            self.assertEqual(queue["review_queue"][0]["review_key"], "review:c")


if __name__ == "__main__":
    unittest.main()
