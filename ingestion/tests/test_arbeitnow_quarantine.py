import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vacature_ingestion.adapters import ADAPTERS
from vacature_ingestion.models import SourceSpec
from vacature_ingestion.runner import IngestionRunner


class FakeClient:
    def __init__(self, records):
        self.records = records
        self.calls = 0

    def get_json(self, url, headers=None):
        self.calls += 1
        return {"data": self.records}


def role(slug="safe", url=None):
    return {
        "slug": slug,
        "url": url or f"https://www.arbeitnow.com/jobs/{slug}",
        "title": "WordPress Developer",
        "company_name": "Example Employer",
        "remote": True,
    }


class ArbeitnowQuarantineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runner = IngestionRunner(Path(self.temp.name) / "state.db")
        self.spec = SourceSpec("arbeitnow-api", "discovery_api", "publicfeeds", "global", max_jobs=80)

    def tearDown(self):
        self.runner.close()
        self.temp.cleanup()

    def test_known_unsafe_record_is_quarantined_while_good_record_survives(self):
        for unsafe in (
            "https://untrusted.example/collect?secret=do-not-log",
            "https://arbeitnow.co.uk/jobs/bad",
            "https://[malformed",
            "http://www.arbeitnow.com/jobs/bad",
        ):
            with self.subTest(url=unsafe):
                result = self.runner.run_source(
                    self.spec, client=FakeClient([role("bad", unsafe), role()]))
                self.assertTrue(result.success)
                self.assertEqual((result.fetched, result.normalized, result.quarantine_count), (2, 1, 1))
                self.assertFalse(result.complete_snapshot)
                self.assertEqual([row["source_job_id"] for row in result.observations], ["global:safe"])
                self.assertEqual(result.summary()["quarantine_count"], 1)
                self.assertFalse(result.summary()["complete_snapshot"])
                self.assertNotIn(unsafe, json.dumps(result.summary()))
                self.assertNotIn("do-not-log", json.dumps(result.observations))

    def test_all_bad_records_remain_explicitly_incomplete_and_counts_do_not_leak_between_runs(self):
        result = self.runner.run_source(self.spec, client=FakeClient([
            role("one", "https://untrusted.example/jobs/1"),
            role("two", "https://arbeitnow.co.uk/jobs/2"),
        ]))
        self.assertTrue(result.success)
        self.assertEqual((result.fetched, result.normalized, result.quarantine_count), (2, 0, 2))
        self.assertFalse(result.complete_snapshot)
        self.assertEqual(result.observations, [])
        self.assertEqual(result.review_observations, [])
        next_run = self.runner.run_source(self.spec, client=FakeClient([role()]))
        self.assertTrue(next_run.success)
        self.assertEqual((next_run.normalized, next_run.quarantine_count), (1, 0))

    def test_partial_or_fully_quarantined_feed_cannot_mark_existing_job_missing_or_closed(self):
        original = self.runner.run_source(self.spec, client=FakeClient([role("existing")]))
        self.assertEqual(original.new, 1)
        bad = role("bad", "https://untrusted.example/jobs/bad")
        for records in ([bad], [bad], [bad, role("new")], [bad]):
            result = self.runner.run_source(self.spec, client=FakeClient(records))
            self.assertFalse(result.complete_snapshot)
            self.assertEqual((result.missing, result.closed), (0, 0))
        jobs = self.runner.state.list_jobs()
        self.assertEqual(len(jobs), 2)
        self.assertTrue(all(job["status"] == "active" for job in jobs))

    def test_offline_ingestion_uses_the_same_partial_snapshot_contract(self):
        self.runner.ingest_records(self.spec, [role("existing")])
        result = self.runner.ingest_records(self.spec, [role("bad", "https://[bad")], complete_snapshot=True)
        self.assertEqual((result.quarantine_count, result.normalized, result.missing, result.closed), (1, 0, 0, 0))
        self.assertFalse(result.complete_snapshot)
        self.assertEqual(self.runner.state.list_jobs()[0]["status"], "active")

    def test_other_feed_url_errors_still_fail_the_source(self):
        spec = SourceSpec("remotejobs-org", "discovery_api", "publicfeeds", "global")
        result = self.runner.run_source(spec, client=FakeClient([
            role("safe", "https://remotejobs.org/jobs/safe"),
            role("bad", "https://untrusted.example/jobs/bad"),
        ]))
        self.assertFalse(result.success)
        self.assertEqual(result.failure_category, "parsing_or_adapter_failure")
        self.assertEqual((result.quarantine_count, result.normalized), (0, 0))
        self.assertEqual(self.runner.state.list_jobs(), [])

    def test_unrecognized_adapter_errors_are_not_swallowed(self):
        adapter = ADAPTERS["publicfeeds"]
        for error in (ValueError("Unexpected employer schema"), TypeError("Invalid provider field")):
            with self.subTest(error=type(error).__name__):
                with patch.object(adapter, "normalize_record", side_effect=error):
                    result = self.runner.run_source(self.spec, client=FakeClient([role()]))
                self.assertFalse(result.success)
                self.assertEqual(result.failure_category, "parsing_or_adapter_failure")
                self.assertEqual(result.quarantine_count, 0)

    def test_same_error_message_from_another_adapter_is_not_quarantinable(self):
        spec = SourceSpec("greenhouse", "ats", "greenhouse", "example")
        adapter = ADAPTERS["greenhouse"]
        with patch.object(adapter, "fetch", return_value=[role()]):
            with patch.object(adapter, "normalize_record", side_effect=ValueError(
                "Unexpected public feed job URL: untrusted_host"
            )):
                result = self.runner.run_source(spec, client=FakeClient([]))
        self.assertFalse(result.success)
        self.assertEqual(result.quarantine_count, 0)


if __name__ == "__main__":
    unittest.main()
