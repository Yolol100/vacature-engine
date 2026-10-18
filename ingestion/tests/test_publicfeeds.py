import unittest

from vacature_ingestion.adapters import ADAPTERS
from vacature_ingestion.models import SourceSpec


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_json(self, url, headers=None):
        self.calls.append(url)
        if url == "https://www.arbeitnow.com/api/job-board-api":
            return {"data": [
                {"slug": "wp-remote", "title": "Remote WordPress Developer", "remote": True,
                 "url": "https://www.arbeitnow.com/jobs/wp-remote", "location": "Europe",
                 "company_name": "Example"},
                {"slug": "on-site", "title": "WordPress Developer", "remote": False,
                 "url": "https://www.arbeitnow.com/jobs/on-site", "location": "Berlin"},
            ]}
        if url == "https://remotelanders.com/api/jobs?category=Engineering&limit=50":
            return {"jobs": [{"slug": "remote-wp", "title": "Remote WordPress Developer",
                              "company": "Example", "location": "Worldwide",
                              "url": "https://remotelanders.com/jobs/remote-wp"}]}
        if url == "https://remotelanders.com/api/jobs?category=Design&limit=50":
            return {"jobs": []}
        if url == "https://remotejobs.org/api/v1/jobs?q=wordpress&limit=30&offset=0":
            return {"data": [{"id": "1", "title": "Remote WordPress Developer",
                              "company": {"name": "Example"}, "location": "Europe",
                              "url": "https://remotejobs.org/remote-jobs/wp"}],
                    "pagination": {"has_more": False}}
        if url == "https://remotejobs.org/api/v1/jobs?q=automation&limit=30&offset=0":
            return {"data": [], "pagination": {"has_more": False}}
        raise AssertionError("Unexpected public API URL")


def spec(source_id, max_jobs=120):
    return SourceSpec(source_id, "discovery_api", "publicfeeds", "global",
                      max_jobs=max_jobs, listing_language="en")


class PublicFeedsTests(unittest.TestCase):
    def test_only_read_only_documented_public_urls(self):
        adapter = ADAPTERS["publicfeeds"]
        expected = {"arbeitnow-api": 1, "remote-landers-api": 2, "remotejobs-org": 2}
        for source, calls in expected.items():
            client = FakeClient()
            rows = adapter.fetch(client, spec(source))
            self.assertEqual(1, len(rows), source)
            self.assertEqual(calls, len(client.calls))
            self.assertTrue(all(uri.startswith("https://") for uri in client.calls))
            result = adapter.normalize_record(rows[0], spec(source), "")
            self.assertTrue(result["source_metadata"]["discovery_only"])
            self.assertEqual(result["source_id"], source)
            self.assertIn("WordPress", result["title"])
            self.assertTrue(result["remote"])

    def test_arbeitnow_apex_and_www_are_allowed_but_lookalikes_fail(self):
        adapter = ADAPTERS["publicfeeds"]
        for url in ("https://arbeitnow.com/jobs/official-role",
                    "https://www.arbeitnow.com/jobs/official-role",
                    "https://www.arbeitnow.co.uk/jobs/official-role"):
            result = adapter.normalize_record({
                "slug": "official-role", "title": "Remote WordPress Developer",
                "url": url, "remote": True, "location": "Europe",
            }, spec("arbeitnow-api"), "")
            self.assertEqual(result["url"], url)
        for url in ("http://arbeitnow.com/jobs/role",
                    "https://arbeitnow.com.evil.example/jobs/role",
                    "https://www.arbeitnow.co.uk.evil.example/jobs/role",
                    "https://arbeitnow.co.uk/jobs/role",
                    "https://other.example/jobs/role",
                    "https://user:password@arbeitnow.com/jobs/role"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "Unexpected public feed job URL"):
                adapter.normalize_record({"title": "WordPress Developer", "url": url},
                                         spec("arbeitnow-api"), "")

    def test_arbeitnow_rejection_has_safe_fixed_diagnostic_categories(self):
        adapter = ADAPTERS["publicfeeds"]
        cases = (
            ("http://www.arbeitnow.com/jobs/role", "malformed"),
            ("https://user:password@www.arbeitnow.com/jobs/role", "malformed"),
            ("https://arbeitnow.co.uk/jobs/role", "uk_apex"),
            ("https://arbeitnow.co.uk.evil.test/jobs/role", "untrusted_host"),
            ("https://untrusted.example/jobs/role", "untrusted_host"),
        )
        for url, category in cases:
            with self.subTest(category=category):
                with self.assertRaises(ValueError) as caught:
                    adapter.normalize_record(
                        {"slug": "role", "title": "Remote WordPress Developer",
                         "url": url, "remote": True}, spec("arbeitnow-api"), "")
                self.assertEqual(str(caught.exception),
                                 "Unexpected public feed job URL: " + category)
                self.assertNotIn("evil.test", str(caught.exception))
                self.assertNotIn("untrusted.example", str(caught.exception))

    def test_no_arbitrary_endpoints_or_unapproved_source_ids(self):
        adapter = ADAPTERS["publicfeeds"]
        client = FakeClient()
        with self.assertRaisesRegex(ValueError, "Unsupported public feed source contract"):
            adapter.fetch(client, spec("evil.example"))
        bad = SourceSpec("remotejobs-org", "discovery_api", "publicfeeds", "global",
                         endpoint="https://example.org/private")
        with self.assertRaisesRegex(ValueError, "Unsupported public feed source contract"):
            adapter.fetch(client, bad)
        self.assertEqual(client.calls, [])

    def test_provider_response_contract_fails_closed(self):
        adapter = ADAPTERS["publicfeeds"]
        class Invalid(FakeClient):
            def get_json(self, url, headers=None):
                return {"error": "rate limited"}
        with self.assertRaisesRegex(ValueError, "Invalid RemoteJobs.org response"):
            adapter.fetch(Invalid(), spec("remotejobs-org"))

    def test_malicious_listing_urls_are_rejected(self):
        adapter = ADAPTERS["publicfeeds"]
        malicious = {"id": "bad", "title": "WordPress Developer", "url": "https://evil.example/jobs/1"}
        for source in ("remotejobs-org", "remote-landers-api", "arbeitnow-api"):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, "Unexpected public feed job URL"):
                    adapter.normalize_record(malicious, spec(source), "")

    def test_global_caps_and_duplicate_provider_identifiers(self):
        adapter = ADAPTERS["publicfeeds"]
        class Duplicate(FakeClient):
            def get_json(self, url, headers=None):
                self.calls.append(url)
                return {"data": [{"id": "1", "url": "https://remotejobs.org/remote-jobs/wp",
                                  "title": "WordPress Developer"}]}
        client = Duplicate()
        result = adapter.fetch(client, spec("remotejobs-org", max_jobs=80))
        self.assertEqual(len(result), 1)
        self.assertEqual(len(client.calls), 2)


if __name__ == "__main__":
    unittest.main()
