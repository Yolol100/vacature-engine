"""No-network regression tests for optional free Google discovery and ATS hints."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from vacature_ingestion.ats_resolver import resolve_ats_url
from vacature_ingestion.adapters.serpapi_google import SerpApiGoogleAdapter
from vacature_ingestion.http import FetchError
from vacature_ingestion.models import SourceSpec
from vacature_ingestion.runner import IngestionRunner


def spec(**opts):
    return SourceSpec("google-jobs", "discovery", "serpapi_google", "worldwide",
                      max_jobs=100, options={"queries": ["WordPress remote"], "max_pages": 2,
                                             "max_requests_per_run": 2, "free_quota_reserve": 10, **opts})


class FreeDiscoveryTests(unittest.TestCase):
    def test_resolves_only_valid_ats_tenants(self):
        self.assertEqual(resolve_ats_url("https://jobs.ashbyhq.com/Eneba/abc")["account"], "Eneba")
        self.assertEqual(resolve_ats_url("https://syde.jobs.personio.com/job/123")["provider"], "personio")
        self.assertEqual(resolve_ats_url("https://jobs.lever.co/kinsta/xyz")["provider"], "lever")
        for url in ("http://jobs.ashbyhq.com/evil", "https://jobs.ashbyhq.com.evil.test/foo",
                    "https://jobs.ashbyhq.com/%2e%2e/job", "https://apply.workable.com/j/1234",
                    "https://user:password@jobs.ashbyhq.com/acme", "javascript:alert(1)"):
            self.assertIsNone(resolve_ats_url(url), url)

    def test_no_key_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(FetchError) as result:
                SerpApiGoogleAdapter().fetch(None, spec())
            self.assertEqual(result.exception.category, "not_configured")

    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_refuses_paid_or_unknown_plan(self, get):
        for account in ({"plan_name": "Developer", "total_searches_left": 5000},
                        {"plan_name": "Free"}, {"plan_name": "Free", "total_searches_left": 1}):
            with self.subTest(account=account), patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
                get.return_value = account
                with self.assertRaises(FetchError) as result:
                    SerpApiGoogleAdapter().fetch(None, spec())
                self.assertEqual(result.exception.category, "free_quota_blocked")

    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_pages_are_bounded_and_never_infer_date(self, get):
        get.side_effect = [
            {"plan_name": "Free", "total_searches_left": 200},
            {"organic_results": [{"title": "WordPress Dev", "link": "https://jobs.ashbyhq.com/acme/42?utm_source=google",
                                  "snippet": "remote"}]},
            {"organic_results": []},
        ]
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            a = SerpApiGoogleAdapter()
            observations = a.normalize_records(a.fetch(None, spec()), spec(), now="2026-10-19T00:00:00Z")
        self.assertEqual(get.call_count, 3)
        self.assertEqual(len(observations), 1)
        job = observations[0]
        self.assertEqual(job["canonical_url"], "https://jobs.ashbyhq.com/acme/42")
        self.assertIsNone(job["published_at"])
        self.assertIsNone(job["remote"])
        self.assertEqual(job["source_metadata"]["ats_hint"]["provider"], "ashby")
        self.assertTrue(job["source_metadata"]["discovery_only"])

    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_never_fetch_more_than_request_cap(self, get):
        get.side_effect = [
            {"plan_name": "Free", "total_searches_left": 200},
            {"organic_results": [{"title": "Job A", "link": "https://example.org/jobs/1"}]},
            {"organic_results": [{"title": "Job B", "link": "https://example.org/jobs/2"}]},
        ]
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            result = SerpApiGoogleAdapter().fetch(None, spec(max_pages=10))
        self.assertEqual(len(result), 2)
        self.assertEqual(get.call_count, 3)

    def test_discovery_incomplete_snapshot_cannot_close_jobs(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as tmp:
            runner = IngestionRunner(Path(tmp) / "state.sqlite")
            adapter = SerpApiGoogleAdapter()
            rows = [{"title": "WordPress Engineer", "url": "https://jobs.ashbyhq.com/acme/123"}]
            rows2 = [{"title": "WordPress Engineer", "url": "https://jobs.ashbyhq.com/acme/456"}]
            with patch.object(adapter, "fetch", side_effect=[rows, rows2]), patch.dict(
                "vacature_ingestion.runner.ADAPTERS", {"serpapi_google": adapter}
            ):
                first = runner.run_source(spec())
                second = runner.run_source(spec())
            self.assertTrue(first.success)
            self.assertTrue(second.success)
            self.assertEqual(second.closed, 0)
            self.assertEqual(second.missing, 0)
            runner.close()


if __name__ == "__main__":
    unittest.main()
