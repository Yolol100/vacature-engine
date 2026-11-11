"""Offline tests for the registered WordPress Jobs RSS discovery route."""
import unittest
from unittest.mock import Mock

from vacature_ingestion.adapters.wordpressjobs import WordPressJobsAdapter
from vacature_ingestion.models import SourceSpec
from scripts.one_pass_vacancies import select_free_specs


class WordPressJobsAdapterTests(unittest.TestCase):
    def spec(self, account="development", url=None):
        return SourceSpec(
            source_id="wordpress-jobs", source_type="wordpress_discovery",
            adapter="wordpressjobs", account=account,
            endpoint=url or f"https://jobs.wordpress.net/job_category/{account}/feed/",
            listing_language="en", max_jobs=20, options={"discovery_only": True},
        )

    def test_official_rss_yields_unverified_job_observations(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel>
          <title>WordPress Jobs Development</title>
          <item>
            <title>Senior WordPress Developer</title>
            <link>https://jobs.wordpress.net/job/senior-wordpress-developer-22/</link>
            <guid>job-123</guid>
            <company>Demo Agency</company>
            <job_location>Remote</job_location>
            <pubDate>Wed, 11 Nov 2026 09:00:00 GMT</pubDate>
            <description><![CDATA[<p>Build WooCommerce sites.</p>]]></description>
          </item>
        </channel></rss>'''
        client = Mock()
        client.get_text.return_value = xml
        adapter = WordPressJobsAdapter()
        spec = self.spec()
        raw = adapter.fetch(client, spec)
        rows = adapter.normalize_records(raw, spec, now="2026-11-12T00:00:00+00:00")
        self.assertEqual(len(rows), 1)
        job = rows[0]
        self.assertEqual(job["source_id"], "wordpress-jobs")
        self.assertEqual(job["source_type"], "wordpress_discovery")
        self.assertEqual(job["title"], "Senior WordPress Developer")
        self.assertEqual(job["employer"], "Demo Agency")
        self.assertEqual(job["published_at"], "2026-11-11T09:00:00+00:00")
        self.assertEqual(job["remote"], None)
        self.assertEqual(job["workplace_type"], None)
        self.assertTrue(job["source_metadata"]["original_employer_publication_unverified"])
        self.assertTrue(job["source_metadata"]["remote_from_netherlands_unverified"])
        self.assertFalse(adapter.complete_snapshot)
        self.assertEqual(client.get_text.call_count, 1)

    def test_rejects_unpinned_endpoint_before_request(self):
        adapter = WordPressJobsAdapter()
        client = Mock()
        with self.assertRaises(ValueError):
            adapter.fetch(client, self.spec(
                url="https://attacker.example.com/feed/"))
        client.get_text.assert_not_called()

    def test_bad_xml_is_not_mistaken_for_empty_jobs(self):
        client = Mock()
        client.get_text.return_value = "<html>not RSS</html>"
        with self.assertRaises(ValueError):
            WordPressJobsAdapter().fetch(client, self.spec())
        client.get_text.return_value = "<rss><channel><item>"
        with self.assertRaises(ValueError):
            WordPressJobsAdapter().fetch(client, self.spec())

    def test_source_active_registry_gates_technical_feed(self):
        specs = [self.spec("development"), self.spec("design")]
        raw = [
            {"source_id": s.source_id, "source_type": s.source_type,
             "adapter": s.adapter, "account": s.account, "endpoint": s.endpoint}
            for s in specs
        ]
        cfg = {"direct_discovery_order": "wordpress_discovery,ats",
               "high_source_order": "wordpress-jobs"}
        t = {"Bronnen": [{"source_id": "wordpress-jobs",
                          "status": "active", "priority": "high"}]}
        active = select_free_specs(raw, t, cfg, limit=5)
        self.assertEqual({x.account for x in active}, {"development", "design"})
        t["Bronnen"].append({"source_id": "ashby", "status": "active", "priority": "low"})
        t["Bronnen"][0]["status"] = "retired"
        self.assertEqual(select_free_specs(raw, t, cfg, limit=5), [])


if __name__ == "__main__":
    unittest.main()
