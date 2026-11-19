from dataclasses import replace
import unittest

from vacature_ingestion.adapters import ADAPTERS
from vacature_ingestion.models import SourceSpec


ENDPOINT = "https://careers.servebolt.com/jobs.rss"
SPEC = SourceSpec(
    source_id="teamtailor", source_type="ats", adapter="teamtailor", account="servebolt",
    endpoint=ENDPOINT, options={"registry_source_id": "company-servebolt"},
)
URL = "https://careers.servebolt.com/jobs/123-wordpress-developer"
FIXTURE = (
    "<rss><channel><item><title>WordPress Developer</title>"
    f"<link>{URL}</link><remoteStatus>fully</remoteStatus>"
    "<pubDate>Wed, 18 Nov 2026 16:02:43 +0100</pubDate></item></channel></rss>"
)


class Feed:
    def __init__(self, xml):
        self.xml = xml
        self.requests = []

    def get_text(self, url, headers):
        self.requests.append(url)
        return self.xml


class TeamtailorTests(unittest.TestCase):
    adapter = ADAPTERS["teamtailor"]

    def test_feed_is_pinned_and_does_not_certify_date_or_country(self):
        feed = Feed(FIXTURE)
        record, = self.adapter.fetch(feed, SPEC)
        job = self.adapter.normalize_record(record, SPEC, "")
        self.assertEqual(feed.requests, [ENDPOINT])
        self.assertEqual(job["canonical_url"], URL)
        self.assertTrue(job["remote"])
        self.assertEqual(job["location"], "Remote")
        self.assertIsNone(job["published_at"])
        self.assertTrue(job["source_metadata"]["remote_from_netherlands_unverified"])
        self.assertEqual(job["source_metadata"]["registry_source_id"], "company-servebolt")

    def test_different_feed_is_never_fetched(self):
        feed = Feed(FIXTURE)
        with self.assertRaisesRegex(ValueError, "not approved"):
            self.adapter.fetch(feed, replace(SPEC, endpoint="https://other.example/jobs.rss"))
        self.assertEqual(feed.requests, [])

    def test_malformed_and_undeclared_feeds_are_not_empty_successes(self):
        for xml in ("<rss>", "<rss/>", "<!DOCTYPE rss><rss><channel/></rss>"):
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                self.adapter.fetch(Feed(xml), SPEC)
        self.assertEqual(self.adapter.fetch(Feed("<rss><channel/></rss>"), SPEC), [])

    def test_external_and_hybrid_job_rows_are_not_candidates(self):
        for text in (FIXTURE.replace(URL, "https://other.example/jobs/123-wordpress-developer"),
                     FIXTURE.replace("fully", "hybrid"),
                     FIXTURE.replace("fully", "onsite"),
                     FIXTURE.replace("fully", "on-site"),
                     FIXTURE.replace("fully", "on site")):
            record, = self.adapter.fetch(Feed(text), SPEC)
            self.assertIsNone(self.adapter.normalize_record(record, SPEC, ""))
