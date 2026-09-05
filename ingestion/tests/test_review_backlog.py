from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vacature_ingestion.models import SourceSpec
from vacature_ingestion.review_backlog import load_review_backlog
from vacature_ingestion.runner import IngestionRunner


def job(job_id: int) -> dict[str, object]:
    return {
        "id": job_id,
        "title": f"Job {job_id}",
        "content": "WordPress role",
        "absolute_url": f"https://example.test/jobs/{job_id}",
    }


class ReviewBacklogTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.state = Path(self.td.name) / "state.sqlite3"
        self.runner = IngestionRunner(self.state)
        self.spec = SourceSpec("greenhouse", "ats", "greenhouse", "acme", "Acme")

    def tearDown(self):
        self.runner.close()
        self.td.cleanup()

    def test_loads_only_jobs_first_seen_since_cutoff(self):
        self.runner.ingest_records(
            self.spec,
            [job(1)],
            now="2026-09-05T13:33:00+00:00",
        )
        self.runner.ingest_records(
            self.spec,
            [job(1), job(2)],
            now="2026-09-05T13:34:10+00:00",
        )
        rows = load_review_backlog(self.state, since="2026-09-05T13:34:00+00:00")
        self.assertEqual([row["source_job_id"] for row in rows], ["acme:2"])
        self.assertEqual(rows[0]["first_seen_at"], "2026-09-05T13:34:10+00:00")
        self.assertEqual(rows[0]["ingestion_change"], "recovered_pending_review")

    def test_closed_jobs_are_excluded_by_default(self):
        self.runner.ingest_records(
            self.spec,
            [job(2)],
            now="2026-09-05T13:34:10+00:00",
        )
        self.runner.ingest_records(self.spec, [], now="2026-09-05T13:35:00+00:00")
        self.runner.ingest_records(self.spec, [], now="2026-09-05T13:36:00+00:00")
        self.assertEqual(
            load_review_backlog(self.state, since="2026-09-05T13:34:00+00:00"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
