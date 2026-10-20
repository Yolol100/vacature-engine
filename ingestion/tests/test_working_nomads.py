from __future__ import annotations

import unittest

from vacature_ingestion.adapters import ADAPTERS
from vacature_ingestion.models import SourceSpec


ENDPOINT = "https://www.workingnomads.com/api/exposed_jobs/"
ROLE = "https://www.workingnomads.com/job/go/1957823/"
ITEM = {
    "url": ROLE,
    "title": "Remote WordPress Integration Engineer",
    "description": "<p>Build <strong>WordPress</strong> automations.</p>",
    "company_name": "Example Employer",
    "category_name": "Development",
    "tags": "wordpress,automation",
    "location": "Europe",
    "pub_date": "2026-10-20T07:41:37-04:00",
}


class Client:
    def __init__(self, data=None):
        self.data = [ITEM] if data is None else data
        self.calls = []

    def get_json(self, url, headers=None):
        self.calls.append(url)
        return self.data


def spec(max_jobs=60):
    return SourceSpec(
        "working-nomads", "job_board", "publicfeeds", "global",
        max_jobs=max_jobs, listing_language="en"
    )


class WorkingNomadsFeedTests(unittest.TestCase):
    def test_bounded_public_feed_normalizes_without_claiming_official_role(self):
        client = Client()
        adapter = ADAPTERS["publicfeeds"]
        records = adapter.fetch(client, spec())
        self.assertEqual([ENDPOINT], client.calls)
        observations = adapter.normalize_records(records, spec())
        self.assertEqual(1, len(observations))
        obs = observations[0]
        self.assertEqual(ROLE.rstrip("/"), obs["canonical_url"])
        self.assertEqual("global:1957823", obs["source_job_id"])
        self.assertEqual("Example Employer", obs["employer"])
        self.assertEqual("Build WordPress automations.", obs["description"])
        self.assertIsNone(obs["published_at"])
        self.assertIsNone(obs["remote"])
        self.assertIsNone(obs["apply_url"])
        self.assertTrue(obs["source_metadata"]["discovery_only"])
        self.assertTrue(obs["source_metadata"]["original_posting_date_unverified"])
        self.assertEqual(ITEM["pub_date"], obs["source_metadata"]["provider_pub_date"])

    def test_malformed_or_untrusted_role_links_rejected_without_leaking(self):
        malicious = [
            "http://www.workingnomads.com/job/go/1957823/",
            "https://www.workingnomads.com.evil.test/job/go/1957823/",
            "https://user:secret@www.workingnomads.com/job/go/1957823/",
            "https://www.workingnomads.com/jobs/",
            "https://www.workingnomads.com/job/go/abc/",
        ]
        for url in malicious:
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, "Unexpected Working Nomads job URL") as caught:
                    ADAPTERS["publicfeeds"].normalize_record(
                        {**ITEM, "url": url}, spec(), ""
                    )
                self.assertNotIn(url, str(caught.exception))

    def test_unexpected_public_api_shape_fails_closed(self):
        for payload in ({"data": [ITEM]}, None, [], [ITEM, "malformed"]):
            with self.subTest(type=type(payload).__name__, value=str(payload)[:15]):
                with self.assertRaisesRegex(ValueError, "Invalid Working Nomads response"):
                    ADAPTERS["publicfeeds"].fetch(Client(payload), spec())

    def test_source_has_fixed_endpoint_and_no_arbitrary_custom_url(self):
        adapter = ADAPTERS["publicfeeds"]
        other = SourceSpec("working-nomads", "job_board", "publicfeeds", "global",
                           endpoint="https://example.com/private")
        client = Client()
        with self.assertRaisesRegex(ValueError, "Unsupported public feed source contract"):
            adapter.fetch(client, other)
        self.assertEqual([], client.calls)

    def test_dedupe_and_batch_cap_prevent_unbounded_ingestion(self):
        first = dict(ITEM)
        second = {**ITEM, "url": "https://www.workingnomads.com/job/go/1957824/"}
        client = Client([first, first, second, second])
        rows = ADAPTERS["publicfeeds"].fetch(client, spec(max_jobs=2))
        self.assertEqual(2, len(rows))
        self.assertEqual([first["url"], second["url"]], [row["url"] for row in rows])


if __name__ == "__main__":
    unittest.main()
