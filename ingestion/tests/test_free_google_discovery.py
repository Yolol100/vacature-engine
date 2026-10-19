"""Offline regression cases for safely bounded free Google discovery."""
from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from vacature_ingestion.adapters.serpapi_google import (
    SerpApiGoogleAdapter, _get_json, _is_safe_free_account, _safe_candidate_url,
)
from vacature_ingestion.ats_resolver import resolve_ats_url
from vacature_ingestion.http import FetchError
from vacature_ingestion.models import SourceSpec
from vacature_ingestion.runner import IngestionRunner


def free_account(**overrides):
    result = {
        "account_status": "Active", "plan_id": "free", "plan_name": "Free Plan",
        "plan_monthly_price": 0.0, "searches_per_month": 250,
        "plan_searches_left": 200, "total_searches_left": 200,
        "extra_credits": 0, "this_hour_searches": 0,
        "account_rate_limit_per_hour": 50,
    }
    result.update(overrides)
    return result


def spec(**options):
    opts = {
        "queries": ["WordPress remote"], "max_pages": 2,
        "max_requests_per_run": 2, "free_quota_reserve": 10,
    }
    opts.update(options)
    return SourceSpec("google-jobs", "discovery", "serpapi_google",
                      "worldwide", max_jobs=100, options=opts)


class FreeDiscoveryTests(unittest.TestCase):
    def test_valid_ats_accounts_are_hints_not_proof(self):
        self.assertEqual(resolve_ats_url("https://jobs.ashbyhq.com/Eneba/abc")["account"], "Eneba")
        self.assertEqual(resolve_ats_url("https://syde.jobs.personio.com/job/123")["provider"], "personio")
        self.assertEqual(resolve_ats_url("https://jobs.lever.co/kinsta/xyz")["provider"], "lever")

    def test_malicious_or_ambiguous_ats_links_are_rejected(self):
        for url in (
            "http://jobs.ashbyhq.com/evil",
            "https://jobs.ashbyhq.com.evil.test/acme",
            "https://jobs.ashbyhq.com/%2e%2e/job",
            "https://jobs.ashbyhq.com/%252e%252e/job",
            "https://apply.workable.com/j/1234",
            "https://user:secret@jobs.ashbyhq.com/acme",
            "javascript:alert(1)",
        ):
            with self.subTest(url=url):
                self.assertIsNone(resolve_ats_url(url))

    def test_malicious_candidate_links_are_rejected(self):
        for url in (
            "javascript:alert(1)", "http://example.com/job",
            "https://user:pwd@example.com/job", "https://localhost/job",
            "https://127.0.0.1/job", "https://example.com:8443/job",
            "https://example.test/job", "https://example.com:broken/job",
            "https://foo.localhost/job", "https://sub.foo.localhost/job",
            "https://127.1/job", "https://0177.0.0.1/job", "https://0x7f000001/job",
            "https://10.0.0.1/job", "https://192.168.1.50/job", "https://[::1]/job",
        ):
            with self.subTest(url=url):
                self.assertIsNone(_safe_candidate_url(url))

    def test_no_api_key_is_safe_failure(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(FetchError) as error:
                SerpApiGoogleAdapter().fetch(None, spec())
        self.assertEqual(error.exception.category, "not_configured")

    def test_not_free_and_ambiguous_accounts_cannot_spend(self):
        invalid = (
            {"plan_name": "Developer Plan"},
            {"plan_name": "Not Free"},
            {"plan_name": "Free Trial"},
            {"plan_id": "developer"},
            {"plan_id": "free-premium"},
            {"plan_monthly_price": 0.01},
            {"plan_monthly_price": None},
            {"searches_per_month": 1000},
            {"plan_searches_left": 1},
            {"total_searches_left": 1},
            {"extra_credits": 3},
            {"account_status": "Paused"},
            {"account_rate_limit_per_hour": 1, "this_hour_searches": 1},
            {"account_rate_limit_per_hour": "50"},
            {"account_rate_limit_per_hour": None},
            {"this_hour_searches": None},
            {"account_rate_limit_per_hour": 0},
            {"this_hour_searches": -1},
        )
        for change in invalid:
            with self.subTest(change=change):
                self.assertFalse(_is_safe_free_account(free_account(**change), 2, 10))

    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_invalid_accounts_never_start_search(self, get):
        get.return_value = free_account(plan_monthly_price=5.0)
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            with self.assertRaises(FetchError) as err:
                SerpApiGoogleAdapter().fetch(None, spec())
        self.assertEqual(err.exception.category, "free_quota_blocked")
        self.assertEqual(get.call_count, 1)  # Free account lookup only.

    def test_zero_search_account_check_needs_no_monthly_reserve(self):
        account = free_account(
            plan_searches_left=0, total_searches_left=0,
            this_hour_searches=50, account_rate_limit_per_hour=50,
        )
        self.assertTrue(_is_safe_free_account(account, 0, 0))
        self.assertFalse(_is_safe_free_account(account, 1, 10))

    def test_valid_free_account_must_keep_reserve(self):
        self.assertTrue(_is_safe_free_account(free_account(total_searches_left=12, plan_searches_left=12), 2, 10))
        self.assertFalse(_is_safe_free_account(free_account(total_searches_left=11), 2, 10))

    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_pages_and_canonical_urls_never_infer_post_date(self, get):
        get.side_effect = [
            free_account(),
            {"organic_results": [
                {"title": "WordPress Engineer", "link": "https://jobs.ashbyhq.com/acme/42?utm_source=google",
                 "snippet": "Remote position"}
            ]},
            {"organic_results": []},
        ]
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            adapter = SerpApiGoogleAdapter()
            rows = adapter.fetch(None, spec())
            observed = adapter.normalize_records(rows, spec(), now="2026-10-19T00:00:00Z")
        self.assertEqual(get.call_count, 3)
        self.assertEqual(len(observed), 1)
        entry = observed[0]
        self.assertEqual(entry["canonical_url"], "https://jobs.ashbyhq.com/acme/42")
        self.assertIsNone(entry["published_at"])
        self.assertIsNone(entry["remote"])
        self.assertIsNone(entry["employer"])
        self.assertTrue(entry["source_metadata"]["discovery_only"])
        self.assertEqual(entry["source_metadata"]["ats_hint"]["provider"], "ashby")

    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_round_robin_fairness_and_hard_request_cap(self, get):
        urls = []
        def source(url, *, timeout):
            if "account.json" in url:
                return free_account()
            query = parse_qs(urlsplit(url).query)
            urls.append((query["q"][0], int(query["start"][0])))
            return {"organic_results": [{
                "title": "Position", "link": "https://example.org/jobs/" + str(len(urls))
            }]}
        get.side_effect = source
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            rows = SerpApiGoogleAdapter().fetch(None, spec(
                queries=["query alpha", "query beta"],
                max_pages=10, max_requests_per_run=4
            ))
        self.assertEqual(len(rows), 4)
        self.assertEqual(urls, [
            ("query alpha", 0), ("query beta", 0),
            ("query alpha", 10), ("query beta", 10),
        ])

    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_tracking_variations_and_duplicate_pages_are_skipped(self, get):
        get.side_effect = [
            free_account(),
            {"organic_results": [{"title": "Job", "link": "https://example.org/jobs/1?utm_source=google"},
                                 {"title": "Job", "link": "https://example.org/jobs/1"}]},
            {"organic_results": [{"title": "Job", "link": "https://example.org/jobs/1?utm_campaign=repeat"}]},
        ]
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            rows = SerpApiGoogleAdapter().fetch(None, spec(max_pages=10))
        self.assertEqual(len(rows), 1)
        self.assertEqual(get.call_count, 3)

    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_time_range_day_does_not_imply_employer_post_date(self, get):
        requests = []
        def source(url, *, timeout):
            requests.append(url)
            return free_account() if "account.json" in url else {"organic_results": []}
        get.side_effect = source
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            SerpApiGoogleAdapter().fetch(None, spec(time_range="day", max_pages=1))
        self.assertEqual(parse_qs(urlsplit(requests[1]).query)["tbs"], ["qdr:d"])

    def test_bad_options_are_rejected_before_spending(self):
        for options in (
            {"queries": [""]}, {"queries": []}, {"max_pages": 11},
            {"max_requests_per_run": 0}, {"max_requests_per_run": True},
            {"free_quota_reserve": -1}, {"time_range": "month"},
        ):
            with self.subTest(options=options), patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
                with patch("vacature_ingestion.adapters.serpapi_google._get_json") as get:
                    with self.assertRaises(ValueError):
                        SerpApiGoogleAdapter().fetch(None, spec(**options))
                    get.assert_not_called()

    def test_provider_http_error_does_not_print_secret(self):
        secret = "top-secret-shall-not-leak"
        url = "https://serpapi.com/account.json?api_key=" + secret
        with patch("vacature_ingestion.adapters.serpapi_google.urlopen",
                   side_effect=HTTPError(url, 403, "unauthorized", {}, None)):
            with self.assertRaises(FetchError) as err:
                _get_json(url, timeout=1)
        self.assertNotIn(secret, str(err.exception))
        self.assertEqual(err.exception.status, 403)

    def test_missing_source_contract_is_rejected(self):
        bad = SourceSpec("random-google-source", "discovery", "serpapi_google", "worldwide")
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            with self.assertRaises(ValueError):
                SerpApiGoogleAdapter().fetch(None, bad)

    def test_partial_google_run_does_not_close_old_jobs(self):
        with tempfile.TemporaryDirectory() as td:
            runner = IngestionRunner(Path(td) / "state.sqlite3")
            adapter = SerpApiGoogleAdapter()
            first = [{"title": "WP Developer", "url": "https://jobs.ashbyhq.com/acme/1"}]
            second = [{"title": "WP Developer", "url": "https://jobs.ashbyhq.com/acme/2"}]
            with patch.object(adapter, "fetch", side_effect=[first, second]), patch.dict(
                "vacature_ingestion.runner.ADAPTERS", {"serpapi_google": adapter}
            ):
                initial = runner.run_source(spec())
                changed = runner.run_source(spec())
            self.assertTrue(initial.success)
            self.assertTrue(changed.success)
            self.assertEqual(changed.closed, 0)
            self.assertEqual(changed.missing, 0)
            self.assertEqual(len(runner.state.list_jobs()), 2)
            runner.close()

    def test_manual_ingest_cannot_override_google_partial_contract(self):
        with tempfile.TemporaryDirectory() as td:
            runner = IngestionRunner(Path(td) / "state.sqlite3")
            first = [{"title": "WP Developer", "url": "https://example.org/job/1"}]
            second = [{"title": "WP Developer", "url": "https://example.org/job/2"}]
            runner.ingest_records(spec(), first, complete_snapshot=True)
            changed = runner.ingest_records(spec(), second, complete_snapshot=True)
            self.assertEqual((changed.missing, changed.closed), (0, 0))
            runner.close()


    def test_manual_workflow_cannot_run_on_schedule_or_pull_request(self):
        workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/free-google-discovery.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("filter-specs", workflow)

    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_repeating_query_terms_do_not_spend_extra_requests(self, get):
        get.side_effect = [
            free_account(),
            {"organic_results": [{"title": "Job", "link": "https://example.org/job/123"}]},
        ]
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            rows = SerpApiGoogleAdapter().fetch(None, spec(
                queries=["wordpress remote", "wordpress remote"],
                max_pages=1, max_requests_per_run=2,
            ))
        self.assertEqual(len(rows), 1)
        self.assertEqual(get.call_count, 2)

    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_documented_empty_success_continues_other_queries(self, get):
        # SerpApi uses an error field for a successful search with no hits.
        get.side_effect = [
            free_account(),
            {
                "search_metadata": {"status": "Success"},
                "search_information": {"organic_results_state": "Fully empty"},
                "error": "Google hasn't returned any results for this query.",
            },
            {"organic_results": [
                {"title": "WordPress Engineer",
                 "link": "https://jobs.ashbyhq.com/acme/42"},
            ]},
        ]
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            results = SerpApiGoogleAdapter().fetch(None, spec(
                queries=["query alpha", "query beta"],
                max_pages=10, max_requests_per_run=2,
            ))
        self.assertEqual(get.call_count, 3)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["query"], "query beta")
        self.assertEqual(results[0]["page"], 1)

    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_confirmed_empty_with_explicit_empty_organic_list(self, get):
        get.side_effect = [
            free_account(),
            {
                "error": "Google hasn't returned any results for this query.",
                "search_metadata": {"status": "Success"},
                "search_information": {"organic_results_state": "Fully empty"},
                "organic_results": [],
            },
        ]
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            result = SerpApiGoogleAdapter().fetch(None, spec(
                max_pages=1, max_requests_per_run=1,
            ))
        self.assertEqual(result, [])
        self.assertEqual(get.call_count, 2)

    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_empty_error_requires_success_and_fully_empty_evidence(self, get):
        message = "Google hasn't returned any results for this query."
        valid = {
            "error": message,
            "search_metadata": {"status": "Success"},
            "search_information": {"organic_results_state": "Fully empty"},
        }
        failures = [
            {"error": message},
            {**valid, "search_metadata": {"status": "Error"}},
            {**valid, "search_information": {"organic_results_state": "Unknown"}},
            {**valid, "organic_results": [
                {"title": "Do not ignore", "link": "https://example.org/1"},
            ]},
            {**valid, "error": "Authentication failed"},
        ]
        for payload in failures:
            with self.subTest(payload=payload), patch.dict(
                os.environ, {"SERPAPI_API_KEY": "test"}
            ):
                get.reset_mock()
                get.side_effect = [free_account(), payload]
                with self.assertRaises(FetchError) as error:
                    SerpApiGoogleAdapter().fetch(None, spec(
                        max_pages=1, max_requests_per_run=1,
                    ))
                self.assertEqual(error.exception.category, "provider_error")
                self.assertEqual(get.call_count, 2)

    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_malformed_search_results_fail_closed(self, get):
        get.side_effect = [free_account(), {"organic_results": {"url": "bad"}}]
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            with self.assertRaises(FetchError) as error:
                SerpApiGoogleAdapter().fetch(None, spec(max_pages=1, max_requests_per_run=1))
        self.assertEqual(error.exception.category, "malformed_result")


    @patch("vacature_ingestion.adapters.serpapi_google._get_json")
    def test_repeating_second_page_does_not_hide_third_page(self, get):
        calls = []
        def fake(url, *, timeout):
            if "account.json" in url:
                return free_account()
            start = int(parse_qs(urlsplit(url).query)["start"][0])
            calls.append(start)
            return {"organic_results": [{
                "title": "Position",
                "link": "https://example.org/job/" + ("first" if start < 20 else "third"),
            }]}
        get.side_effect = fake
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test"}):
            jobs = SerpApiGoogleAdapter().fetch(None, spec(
                max_pages=3, max_requests_per_run=3
            ))
        self.assertEqual(calls, [0, 10, 20])
        self.assertEqual(len(jobs), 2)

    def test_google_ten_pages_configuration_can_hold_all_candidates(self):
        import json
        specs = json.loads((Path(__file__).resolve().parents[1] /
                            "source-specs.google-optional.json").read_text(encoding="utf-8"))
        self.assertEqual(len(specs), 1)
        cfg = specs[0]
        self.assertEqual(cfg["source_id"], "google-jobs")
        self.assertGreaterEqual(
            cfg["max_jobs"], len(cfg["options"]["queries"]) *
            cfg["options"]["max_pages"] * 10
        )


    def test_google_discovery_must_not_overwrite_or_resurrect_official_job(self):
        import json
        employer = SourceSpec("greenhouse", "ats", "greenhouse", "acme", employer="Acme")
        detail = {
            "id": 42, "title": "Senior WordPress Engineer",
            "absolute_url": "https://careers.example.org/jobs/42",
            "content": "<p>Verified employer description with full responsibilities.</p>",
            "location": {"name": "Europe"},
        }
        snippet = {
            "title": "Senior WordPress Engineer",
            "url": "https://careers.example.org/jobs/42",
            "snippet": "A short Google excerpt that is not official evidence.",
        }
        with tempfile.TemporaryDirectory() as td:
            runner = IngestionRunner(Path(td) / "test.sqlite")
            try:
                official = runner.ingest_records(employer, [detail])
                self.assertTrue(official.success)
                original = runner.state.list_jobs()[0]
                original_payload = json.loads(original["payload_json"])
                original_snapshots = runner.state.snapshot_count()
                google = runner.ingest_records(spec(), [snippet], complete_snapshot=True)
                self.assertTrue(google.success)
                self.assertEqual(google.updated, 0)
                self.assertEqual(google.review_observations, [])
                observed = runner.state.list_jobs()[0]
                self.assertEqual(json.loads(observed["payload_json"]), original_payload)
                self.assertEqual(runner.state.snapshot_count(), original_snapshots)

                # Only the authoritative employer can close the vacancy.
                runner.ingest_records(employer, [])
                closed = runner.ingest_records(employer, [])
                self.assertEqual(closed.closed, 1)
                self.assertEqual(runner.state.list_jobs()[0]["status"], "closed")
                runner.ingest_records(spec(), [snippet], complete_snapshot=True)
                self.assertEqual(runner.state.list_jobs()[0]["status"], "closed")
            finally:
                runner.close()

    def test_google_snippet_changes_are_not_job_content_updates(self):
        search = spec()
        first = {"title": "WordPress Developer", "url": "https://example.org/roles/1",
                 "snippet": "SEO excerpt A"}
        changed = dict(first, snippet="SEO excerpt B")
        with tempfile.TemporaryDirectory() as td:
            runner = IngestionRunner(Path(td) / "test.sqlite")
            try:
                a = runner.ingest_records(search, [first])
                self.assertEqual(a.new, 1)
                n = runner.state.snapshot_count()
                b = runner.ingest_records(search, [changed])
                self.assertEqual((b.new, b.updated, b.unchanged), (0, 0, 1))
                self.assertEqual(b.review_observations, [])
                self.assertEqual(runner.state.snapshot_count(), n)
            finally:
                runner.close()


    def test_public_feed_discovery_metadata_updates_without_false_closure(self):
        # PublicFeedsAdapter also sets discovery_only=True; unlike Google
        # snippets, its changing content must create updates and memberships.
        import json
        feed = SourceSpec("remotejobs-org", "job_board", "publicfeeds",
                          "remotejobs-org", listing_language="en")
        first = {
            "id": 42, "title": "WordPress Engineer",
            "url": "https://remotejobs.org/jobs/wordpress-42",
            "description": "First job description",
            "company_name": "Acme",
        }
        second = dict(first, description="Updated official public feed text")
        with tempfile.TemporaryDirectory() as td:
            runner = IngestionRunner(Path(td) / "state.sqlite3")
            try:
                original = runner.ingest_records(feed, [first])
                self.assertTrue(original.success)
                self.assertEqual(original.new, 1)
                payload = json.loads(runner.state.list_jobs()[0]["payload_json"])
                self.assertTrue(payload["source_metadata"]["discovery_only"])
                self.assertEqual(payload["source_metadata"]["provider"], "remotejobs-org")
                count = runner.state.snapshot_count()
                # A stale membership from a previous bounded-feed version
                # must not hide legitimate feed updates during migration.
                feed_job = runner.state.list_jobs()[0]
                runner.state.db.execute(
                    "INSERT INTO source_membership(source_instance,job_id,missing_runs,last_seen_run,close_threshold) VALUES (?,?,?,?,?)",
                    (feed.instance_id, feed_job["job_id"], 0, "legacy-feed", 2),
                )
                runner.state.db.commit()
                change = runner.ingest_records(feed, [second])
                self.assertTrue(change.success)
                self.assertEqual(change.updated, 1)
                self.assertEqual(len(change.review_observations), 1)
                self.assertEqual(runner.state.snapshot_count(), count + 1)
                updated_payload = json.loads(runner.state.list_jobs()[0]["payload_json"])
                self.assertIn("Updated official public feed text", updated_payload["description"])
                skipped_once = runner.ingest_records(feed, [])
                skipped_twice = runner.ingest_records(feed, [])
                self.assertEqual((skipped_once.missing, skipped_once.closed), (0, 0))
                self.assertEqual((skipped_twice.missing, skipped_twice.closed), (0, 0))
                self.assertEqual(runner.state.list_jobs()[0]["status"], "active")
            finally:
                runner.close()

    def test_partial_public_adapters_never_close_jobs_from_omissions(self):
        from vacature_ingestion.adapters import ADAPTERS
        for adapter in ("publicfeeds", "himalayas", "jobicy", "jsonld",
                        "remoteok", "remotive", "weworkremotely", "serpapi_google"):
            with self.subTest(adapter=adapter):
                source = SourceSpec("test-public", "job_board", adapter,
                                    "some-source", max_jobs=500)
                self.assertFalse(ADAPTERS[adapter].is_complete_snapshot(source, []))

    def test_employer_ats_cap_does_not_count_as_full_snapshot(self):
        from vacature_ingestion.adapters import ADAPTERS
        role = {
            "id": 7, "title": "WP Developer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/7",
            "content": "Developer role",
        }
        full = SourceSpec("acme-greenhouse", "ats", "greenhouse", "acme", max_jobs=10)
        capped = SourceSpec("acme-greenhouse", "ats", "greenhouse", "acme", max_jobs=1)
        self.assertTrue(ADAPTERS["greenhouse"].is_complete_snapshot(full, [role]))
        self.assertFalse(ADAPTERS["greenhouse"].is_complete_snapshot(capped, [role]))
        with tempfile.TemporaryDirectory() as td:
            runner = IngestionRunner(Path(td) / "test.sqlite")
            try:
                first = runner.ingest_records(capped, [role])
                other = dict(role, id=8,
                             absolute_url="https://boards.greenhouse.io/acme/jobs/8")
                second = runner.ingest_records(capped, [other])
                self.assertTrue(first.success and second.success)
                self.assertEqual((second.missing, second.closed), (0, 0))
                self.assertEqual(len(runner.state.list_jobs()), 2)
                runner.ingest_records(full, [other])
                definitive = runner.ingest_records(full, [other])
                self.assertEqual(definitive.closed, 1)
            finally:
                runner.close()

    def test_partial_feed_cannot_overwrite_or_reopen_official_role(self):
        import json
        official = SourceSpec("acme-greenhouse", "ats", "greenhouse",
                              "acme", max_jobs=10)
        feed = SourceSpec("remotejobs-org", "job_board", "publicfeeds",
                          "remotejobs-org", max_jobs=10)
        url = "https://remotejobs.org/jobs/42"
        canonical = {
            "id": 42, "title": "WordPress Engineer",
            "absolute_url": url,
            "content": "<p>Employer-confirmed responsibilities.</p>",
        }
        external = {
            "id": 42, "title": "WordPress Engineer",
            "url": url, "description": "Short feed copy",
            "company_name": "Acme",
        }
        with tempfile.TemporaryDirectory() as td:
            runner = IngestionRunner(Path(td) / "test.sqlite")
            try:
                self.assertEqual(runner.ingest_records(official, [canonical]).new, 1)
                before = runner.state.list_jobs()[0]
                original = json.loads(before["payload_json"])
                count = runner.state.snapshot_count()

                # Simulate a stale membership left by the previous version.
                runner.state.db.execute(
                    "INSERT INTO source_membership(source_instance,job_id,missing_runs,last_seen_run,close_threshold) VALUES (?,?,?,?,?)",
                    (feed.instance_id, before["job_id"], 0, "legacy-run", 2),
                )
                runner.state.db.commit()

                observation = runner.ingest_records(feed, [external])
                self.assertEqual(observation.updated, 0)
                self.assertEqual(observation.review_observations, [])
                self.assertEqual(runner.state.snapshot_count(), count)
                self.assertEqual(json.loads(runner.state.list_jobs()[0]["payload_json"]), original)
                old_membership = runner.state.db.execute(
                    "SELECT COUNT(*) FROM source_membership WHERE source_instance=?",
                    (feed.instance_id,),
                ).fetchone()[0]
                self.assertEqual(old_membership, 0)

                runner.ingest_records(official, [])
                closed = runner.ingest_records(official, [])
                self.assertEqual(closed.closed, 1)
                self.assertEqual(runner.state.list_jobs()[0]["status"], "closed")

                # Even after closure, a stale third-party hit cannot revive it.
                repeated = runner.ingest_records(feed, [external])
                self.assertEqual(repeated.updated, 0)
                self.assertEqual(repeated.review_observations, [])
                self.assertEqual(runner.state.list_jobs()[0]["status"], "closed")
            finally:
                runner.close()

    def test_direct_ingest_requires_original_google_source_contract(self):
        bad = SourceSpec("not-google-jobs", "discovery",
                         "serpapi_google", "worldwide")
        row = {
            "title": "WordPress Developer",
            "url": "https://jobs.ashbyhq.com/acme/42",
            "snippet": "Unverified snippet",
        }
        with tempfile.TemporaryDirectory() as td:
            runner = IngestionRunner(Path(td) / "state.sqlite")
            try:
                with self.assertRaises(ValueError):
                    runner.ingest_records(bad, [row])
                self.assertEqual(runner.state.list_jobs(), [])
                self.assertEqual(
                    runner.state.db.execute("SELECT COUNT(*) FROM source_runs").fetchone()[0],
                    0,
                )
            finally:
                runner.close()

    def test_empty_invalid_google_ingest_preserves_official_memberships(self):
        # An empty batch skips per-record validation. It must never be able
        # to impersonate an ATS source and clear its closure-tracking state.
        employer = SourceSpec("greenhouse", "ats", "greenhouse", "acme")
        invalid = SourceSpec("greenhouse", "discovery", "serpapi_google", "acme")
        original = {
            "id": 42, "title": "WordPress Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/42",
        }
        with tempfile.TemporaryDirectory() as td:
            runner = IngestionRunner(Path(td) / "state.sqlite")
            try:
                self.assertEqual(runner.ingest_records(employer, [original]).new, 1)
                rows_before = runner.state.run_rows()
                membership_before = [
                    tuple(row) for row in runner.state.db.execute(
                        "SELECT source_instance, job_id, missing_runs, close_threshold "
                        "FROM source_membership ORDER BY source_instance, job_id"
                    ).fetchall()
                ]
                self.assertEqual(len(membership_before), 1)
                with self.assertRaises(ValueError):
                    runner.ingest_records(invalid, [])
                membership_after = [
                    tuple(row) for row in runner.state.db.execute(
                        "SELECT source_instance, job_id, missing_runs, close_threshold "
                        "FROM source_membership ORDER BY source_instance, job_id"
                    ).fetchall()
                ]
                self.assertEqual(membership_after, membership_before)
                self.assertEqual(runner.state.run_rows(), rows_before)
                self.assertEqual(runner.state.list_jobs()[0]["status"], "active")
            finally:
                runner.close()

    def test_actions_use_immutable_full_commit_ids(self):
        root = Path(__file__).resolve().parents[2]
        paths = (
            root / ".github/workflows/ingestion-tests.yml",
            root / ".github/workflows/free-google-discovery.yml",
        )
        for path in paths:
            for line in path.read_text(encoding="utf-8").splitlines():
                if "uses:" not in line:
                    continue
                action = line.split("uses:", 1)[1].split("#", 1)[0].strip()
                with self.subTest(workflow=path.name, action=action):
                    self.assertRegex(action, r"^actions/[a-z-]+@[0-9a-f]{40}$")



if __name__ == "__main__":
    unittest.main()
