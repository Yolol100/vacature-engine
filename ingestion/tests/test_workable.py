import unittest

from vacature_ingestion.adapters import ADAPTERS
from vacature_ingestion.models import SourceSpec


class WorkableAdapterTests(unittest.TestCase):
    def test_public_feed_and_normalization(self):
        class Client:
            def get_json(self, url):
                self.url = url
                return {
                    "jobs": [{
                        "id": "job-1",
                        "shortcode": "ABC123",
                        "title": "WordPress Developer",
                        "url": "https://apply.workable.com/awesomemotive/j/ABC123/",
                        "application_url": "https://apply.workable.com/awesomemotive/j/ABC123/apply/",
                        "published_on": "2026-09-05T12:00:00Z",
                        "location": {"location_str": "Remote", "telecommuting": True, "workplace_type": "remote"},
                        "description": "Build WordPress products",
                        "salary": {"salary_from": 60000, "salary_to": 80000, "salary_currency": "USD"}
                    }]
                }

        spec = SourceSpec("workable", "ats", "workable", "awesomemotive", "Awesome Motive", listing_language="en")
        client = Client()
        rows = ADAPTERS["workable"].fetch(client, spec)
        self.assertEqual(client.url, "https://www.workable.com/api/accounts/awesomemotive?details=true")
        self.assertEqual(len(rows), 1)
        out = ADAPTERS["workable"].normalize_records(rows, spec)[0]
        self.assertEqual(out["source_job_id"], "awesomemotive:job-1")
        self.assertEqual(out["canonical_url"], "https://apply.workable.com/awesomemotive/j/ABC123")
        self.assertTrue(out["remote"])
        self.assertEqual(out["salary"]["currency"], "USD")


if __name__ == "__main__":
    unittest.main()
