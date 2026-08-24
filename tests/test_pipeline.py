import unittest
from datetime import UTC, datetime, timedelta

from vacature_engine.models import JobRecord
from vacature_engine.pipeline import deduplicate, filter_recency, posted_age_days


class PipelineTests(unittest.TestCase):
    def test_dedupe_tracking_url(self):
        first = JobRecord("x", "1", "Engineer", "Acme", "https://example.com/job/1?utm_source=a")
        second = JobRecord("y", "2", "Engineer", "Acme", "https://example.com/job/1")
        self.assertEqual(len(deduplicate([first, second])), 1)

    def test_unknown_date_not_fresh(self):
        job = JobRecord("x", "1", "Engineer", "Acme", "https://example.com/job/1")
        fresh, unknown = filter_recency([job], 7)
        self.assertEqual(fresh, [])
        self.assertEqual(unknown, [job])

    def test_recent_date(self):
        now = datetime.now(UTC)
        job = JobRecord("x", "1", "Engineer", "Acme", "https://example.com/job/1", posted_at=(now - timedelta(days=2)).isoformat())
        self.assertLess(posted_age_days(job, now=now), 2.01)

    def test_personio_feed_rows_do_not_collapse(self):
        first = JobRecord("personio", "1", "Engineer", "Acme", "https://acme.jobs.personio.de/xml", raw={"requires_canonical_job_resolution": True})
        second = JobRecord("personio", "2", "Designer", "Acme", "https://acme.jobs.personio.de/xml", raw={"requires_canonical_job_resolution": True})
        self.assertEqual(len(deduplicate([first, second])), 2)

    def test_batch_result_serializes_slotted_failures(self):
        from vacature_engine.pipeline import BatchResult, SourceFailure
        result = BatchResult([], [SourceFailure("x", "acme", "blocked/login-required", "blocked", False)])
        self.assertEqual(result.to_dict()["failures"][0]["category"], "blocked/login-required")


if __name__ == "__main__":
    unittest.main()
