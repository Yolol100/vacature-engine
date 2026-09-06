import json
import tempfile
import unittest
from pathlib import Path

from vacature_ingestion.workflow_state import merge_ack_documents, normalize_ack_document, normalize_ack_file


class WorkflowStateTests(unittest.TestCase):
    def test_normalize_ack_preserves_unknown_fields_and_dedupes(self):
        actual = normalize_ack_document({
            "schema_version": "2",
            "acked_keys": ["b", "a", "a", ""],
            "migrations": ["m2", "m1", "m1"],
            "note": "keep",
        })
        self.assertEqual(actual["schema_version"], 2)
        self.assertEqual(actual["acked_keys"], ["a", "b"])
        self.assertEqual(actual["migrations"], ["m1", "m2"])
        self.assertEqual(actual["note"], "keep")

    def test_normalize_invalid_file_falls_back(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ack.json"
            path.write_text("not json", encoding="utf-8")
            actual = normalize_ack_file(path)
            self.assertEqual(actual, {"schema_version": 1, "acked_keys": [], "migrations": []})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), actual)

    def test_merge_ack_unions_keys_and_remote_wins_existing_metadata(self):
        actual = merge_ack_documents(
            {"schema_version": 2, "acked_keys": ["local"], "migrations": ["m1"], "local_only": True, "owner": "local"},
            {"schema_version": 1, "acked_keys": ["remote"], "migrations": ["m2"], "owner": "remote"},
        )
        self.assertEqual(actual["schema_version"], 2)
        self.assertEqual(actual["acked_keys"], ["local", "remote"])
        self.assertEqual(actual["migrations"], ["m1", "m2"])
        self.assertEqual(actual["owner"], "remote")
        self.assertTrue(actual["local_only"])


if __name__ == "__main__":
    unittest.main()
