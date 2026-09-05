import unittest

from vacature_ingestion.adapters import ADAPTERS
from vacature_ingestion.models import SourceSpec


class FastFeedAdapterTests(unittest.TestCase):
    def test_remoteok_skips_terms_row_and_maps_job(self):
        class Client:
            def get_json(self, url, *, headers=None):
                self.url = url
                return [
                    {"last_updated": 123, "legal": "link back"},
                    {
                        "id": "42",
                        "position": "WordPress Engineer",
                        "company": "Acme",
                        "date": "2026-09-05T18:00:00+00:00",
                        "description": "<p>Build WordPress products.</p>",
                        "location": "Worldwide",
                        "apply_url": "https://remoteok.com/remote-jobs/42",
                        "tags": ["wordpress", "php"],
                        "salary_min": 60000,
                        "salary_max": 80000,
                    },
                ]

        spec = SourceSpec(
            "remote-ok",
            "job_board",
            "remoteok",
            "global",
            listing_language="en",
            max_jobs=200,
        )
        client = Client()
        rows = ADAPTERS["remoteok"].fetch(client, spec)
        self.assertEqual(1, len(rows))
        out = ADAPTERS["remoteok"].normalize_records(rows, spec)[0]
        self.assertEqual("global:42", out["source_job_id"])
        self.assertEqual("WordPress Engineer", out["title"])
        self.assertEqual("Worldwide", out["location"])
        self.assertEqual(60000, out["salary"]["min"])
        self.assertTrue(out["source_metadata"]["attribution_required"])
        self.assertTrue(out["source_metadata"]["canonical_verification_required"])

    def test_weworkremotely_parses_public_rss(self):
        class Client:
            def get_text(self, url, *, headers=None):
                self.url = url
                return """<?xml version="1.0" encoding="UTF-8"?>
                <rss version="2.0"><channel><item>
                  <title>Acme: Senior WordPress Developer</title>
                  <link>https://weworkremotely.com/remote-jobs/acme-senior-wordpress-developer</link>
                  <guid>wwr-123</guid>
                  <pubDate>Sat, 05 Sep 2026 18:00:00 +0000</pubDate>
                  <region>Anywhere in the World</region>
                  <category>Programming</category>
                  <description><![CDATA[<p>Build WordPress products.</p>]]></description>
                </item></channel></rss>"""

        spec = SourceSpec(
            "we-work-remotely",
            "job_board",
            "weworkremotely",
            "programming",
            endpoint="https://weworkremotely.com/categories/remote-programming-jobs.rss",
            listing_language="en",
            max_jobs=200,
        )
        client = Client()
        rows = ADAPTERS["weworkremotely"].fetch(client, spec)
        self.assertEqual(1, len(rows))
        out = ADAPTERS["weworkremotely"].normalize_records(rows, spec)[0]
        self.assertEqual("Acme", out["employer"])
        self.assertEqual("Senior WordPress Developer", out["title"])
        self.assertEqual("Anywhere in the World", out["location"])
        self.assertTrue(out["published_at"].startswith("2026-09-05T18:00:00"))
        self.assertTrue(out["source_metadata"]["attribution_required"])
        self.assertTrue(out["source_metadata"]["canonical_verification_required"])


if __name__ == "__main__":
    unittest.main()
