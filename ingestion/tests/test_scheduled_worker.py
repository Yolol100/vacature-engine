"""No-network regression tests for the scheduled public-only worker."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "scheduled_worker.py"
spec = importlib.util.spec_from_file_location("scheduled_worker", PATH)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.src = {"source_id": "company-test", "source_name": "Test Corp",
                    "source_type": "employer_direct", "base_url": "https://jobs.example.com/careers/"}

    def test_public_https_only(self):
        self.assertEqual(worker.safe_url("http://example.com/jobs"), "")
        self.assertEqual(worker.safe_url("https://127.0.0.1/admin"), "")
        self.assertEqual(worker.safe_url("https://10.0.0.5/private"), "")
        self.assertEqual(worker.safe_url("https://localhost/private"), "")
        self.assertEqual(worker.safe_url("https://user:pass@example.com/jobs"), "")
        self.assertEqual(worker.safe_url("https://example.com:4443/jobs"), "")
        self.assertEqual(worker.safe_url("https://example.com/jobs"), "https://example.com/jobs")

    def test_remote_wordpress_schema_job_kept_unverified(self):
        data = {"@context": "https://schema.org", "@type": "JobPosting",
                "title": "WordPress Developer",
                "jobLocationType": "TELECOMMUTE",
                "applicantLocationRequirements": {"name": "Europe"},
                "url": "https://jobs.example.com/careers/123",
                "description": "Build WordPress websites and WooCommerce stores",
                "datePosted": "2026-11-20",
                "hiringOrganization": {"name": "Test Corp"}}
        html = '<script type="application/ld+json">' + json.dumps(data) + "</script>"
        jobs = worker.discover(html, self.src, self.src["base_url"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "WordPress Developer")
        self.assertEqual(jobs[0]["location"], "Remote - Europe")
        self.assertEqual(jobs[0]["review_status"], "unverified")

    def test_hybrid_us_only_unrelated_not_promoted(self):
        for item in [
            {"title": "WordPress Developer", "jobLocationType": "HYBRID"},
            {"title": "WordPress Developer", "jobLocationType": "TELECOMMUTE",
             "applicantLocationRequirements": {"name": "United States only"}},
            {"title": "AI Automation Engineer", "jobLocationType": "TELECOMMUTE"},
        ]:
            item["url"] = "https://jobs.example.com/jobs/1"
            html = '<script type="application/ld+json">' + json.dumps({"@type": "JobPosting", **item}) + "</script>"
            self.assertEqual(worker.discover(html, self.src, self.src["base_url"]), [], item)

    def test_remote_links_must_be_role_specific(self):
        html = '<a href="/jobs">Remote WordPress Jobs</a>' \
               '<a href="/jobs/123">Remote WordPress Developer</a>' \
               '<a href="/jobs/456">WordPress Developer</a>' \
               '<a href="http://private.local/job">Remote WordPress Developer</a>'
        jobs = worker.discover(html, self.src, self.src["base_url"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["url"], "https://jobs.example.com/jobs/123")

    def test_google_redirect_query_extracts_public_link(self):
        url = worker.job_url("/url?q=https%3A%2F%2Fjobs.example.com%2Fjobs%2F123%3Futm_source%3Dgoogle",
                             "https://www.google.com/search")
        self.assertEqual(url, "https://jobs.example.com/jobs/123")

    def test_worker_records_every_id_in_complete_mock_run(self):
        path = Path(__file__).resolve().parents[1] / "sources.public-snapshot.json"
        entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
        self.assertEqual(len(entries), 233)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(worker, "source_check", lambda s: (
                {"source_id": s["source_id"], "status": "http_200",
                 "checked_at": worker.utc_now(), "browser": "not_attempted",
                 "candidate_count": 0, "coverage": "overview_only", "url": s["base_url"]}, [])):
                result = worker.run(path, Path(tmp) / "latest.json", max_render=0, google=False)
            self.assertEqual(result["source_count"], 233)
            self.assertEqual(result["summary"]["attempted"], 233)
            self.assertEqual(len(result["sources"]), 233)
            self.assertEqual(result["summary"]["saved_in_report"], 0)

    def test_public_json_api_remote_role_pending(self):
        raw = json.dumps({"jobs": [
            {"jobTitle": "Remote WordPress Developer",
             "url": "https://jobs.example.com/jobs/431",
             "jobGeo": "Europe", "jobDescription": "Build WooCommerce sites",
             "remote": True},
            {"title": "Elementor Web Designer",
             "url": "https://jobs.example.com/jobs/432",
             "jobGeo": "Hybrid Amsterdam", "remote": False},
        ]})
        rows = worker.discover(raw, self.src, self.src["base_url"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://jobs.example.com/jobs/431")
        self.assertEqual(rows[0]["review_status"], "unverified")

    def test_public_rss_remote_role_pending(self):
        xml = '<rss version="2.0"><channel><item>' \
              '<title>Remote WordPress Developer</title>' \
              '<link>https://jobs.example.com/jobs/501</link>' \
              '<description>Build WooCommerce stores</description>' \
              '<pubDate>Sat, 21 Nov 2026 10:00:00 GMT</pubDate>' \
              '</item></channel></rss>'
        rows = worker.discover(xml, self.src, self.src["base_url"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["location"], "Remote")

    def test_browser_unavailable_is_honest(self):
        self.assertEqual(worker.render_with_chrome("https://example.com/", ""), ("browser_unavailable", ""))


if __name__ == "__main__":
    unittest.main()
