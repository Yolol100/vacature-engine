import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from vacature_engine.models import JobRecord
from vacature_engine.pipeline import (
    SourceSpec,
    deduplicate,
    fetch_many,
    filter_recency,
    posted_age_days,
)


def job(url="https://example.com/1", *, posted_at=None, source="x", source_id="1", description="Same exact body", location="Remote"):
    return JobRecord(
        source=source,
        source_job_id=source_id,
        title="Senior Developer",
        employer="Acme",
        job_url=url,
        location=location,
        description=description,
        posted_at=posted_at,
    )


class PipelineTests(unittest.TestCase):
    def test_dedupe_tracking_url(self):
        self.assertEqual(len(deduplicate([job("https://x.test/1?utm_source=a"), job("https://x.test/1")])) , 1)

    def test_semantic_dedupe_across_urls(self):
        first = job("https://example.com/1", source="a", source_id="1")
        second = job("https://jobs.example.org/2", source="b", source_id="2")
        self.assertEqual(len(deduplicate([first, second])), 1)

    def test_semantic_dedupe_keeps_materially_different_body(self):
        first = job("https://example.com/1", description="WordPress role")
        second = job("https://example.org/2", source_id="2", description="Different Java role")
        self.assertEqual(len(deduplicate([first, second])), 2)

    def test_requires_resolution_rows_do_not_semantic_collapse(self):
        first = job("https://feed.test/xml", source_id="1")
        second = job("https://feed.test/xml", source_id="2")
        first.raw["requires_canonical_job_resolution"] = True
        second.raw["requires_canonical_job_resolution"] = True
        self.assertEqual(len(deduplicate([first, second])), 2)

    def test_recent_date(self):
        now = datetime.now(UTC)
        item = job(posted_at=(now - timedelta(days=2)).isoformat())
        self.assertAlmostEqual(posted_age_days(item, now=now), 2, places=3)
        fresh, unknown = filter_recency([item], 7)
        self.assertEqual(len(fresh), 1)
        self.assertFalse(unknown)

    def test_future_date_is_negative_and_not_fresh(self):
        now = datetime.now(UTC)
        item = job(posted_at=(now + timedelta(days=2)).isoformat())
        self.assertLess(posted_age_days(item, now=now), 0)
        fresh, unknown = filter_recency([item], 7)
        self.assertFalse(fresh)
        self.assertFalse(unknown)

    def test_unknown_date_not_fresh(self):
        fresh, unknown = filter_recency([job(posted_at=None)], 7)
        self.assertFalse(fresh)
        self.assertEqual(len(unknown), 1)

    def test_bad_days_back_rejected(self):
        for value in (-1, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                filter_recency([], value)

    def test_batch_isolates_unexpected_adapter_error(self):
        with patch("vacature_engine.pipeline.fetch_source", side_effect=TypeError("boom")):
            result = fetch_many([SourceSpec("x", "a")])
        self.assertEqual(len(result.failures), 1)
        self.assertIn("TypeError", result.failures[0].message)

    def test_bad_max_workers_rejected(self):
        for value in (0, 9, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                fetch_many([], max_workers=value)

    def test_days_back_nonfinite_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                filter_recency([], value)

    def test_same_source_id_dedupes_even_when_url_changes(self):
        first = job("https://example.com/a", source="greenhouse", source_id="42", description=None, location=None)
        second = job("https://example.com/b", source="greenhouse", source_id="42", description=None, location=None)
        self.assertEqual(deduplicate([first, second]), [first])

    def test_fetch_many_preserves_source_spec_order_despite_completion_order(self):
        specs = [SourceSpec("greenhouse", "a"), SourceSpec("greenhouse", "b")]
        first = job("https://example.com/1", source="greenhouse", source_id="1")
        second = job("https://example.com/2", source="greenhouse", source_id="2", description="Different body")

        def fake_fetch(spec):
            import time
            if spec.slug == "a":
                time.sleep(0.02)
                return [first]
            return [second]

        with patch("vacature_engine.pipeline.fetch_source", side_effect=fake_fetch):
            result = fetch_many(specs, max_workers=2)
        self.assertEqual([item.source_job_id for item in result.jobs], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
