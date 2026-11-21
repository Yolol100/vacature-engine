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

    def test_listing_pages_marketing_and_us_based_are_not_job_leads(self):
        titles = [
            ("Remote WordPress Jobs", "https://example.com/remote-jobs/wordpress"),
            ("Browse more remote WordPress jobs", "https://example.com/jobs?skills=WordPress"),
            ("Frontend Developer Remote Jobs", "https://example.com/remote-frontend-developer-jobs"),
            ("Remote Frontend Jobs in USA", "https://example.com/remote-frontend-jobs-usa"),
            ("WordPress Plugin Growth Marketer - Remote", "https://example.com/jobs/marketer"),
            ("WordPress Sales Support Specialist Remote", "https://example.com/jobs/sales"),
            ("Web Developer: WordPress & HubSpot (U.S. Based, Remote Contractor)",
             "https://example.com/jobs/usa"),
            ("Frontend Developer (Remote Friendly)", "https://example.com/jobs/hybrid"),
        ]
        for title, url in titles:
            with self.subTest(title=title):
                data = '<a href="' + url + '">' + title + '</a>'
                self.assertEqual(worker.discover(data, self.src, self.src["base_url"]), [])
        ok = '<a href="https://example.com/jobs/123">Remote WordPress Support Specialist</a>'
        self.assertEqual(len(worker.discover(ok, self.src, self.src["base_url"])), 1)

    def test_google_account_only_zero_price_free_plan_passes(self):
        free = {
            "account_status": "Active", "plan_id": "free",
            "plan_name": "Free Plan", "plan_monthly_price": 0,
            "searches_per_month": 250, "plan_searches_left": 120,
            "total_searches_left": 120, "extra_credits": 0,
            "account_rate_limit_per_hour": 50, "this_hour_searches": 0
        }
        self.assertEqual(worker.free_serpapi_account_status(free), "free_verified")
        for updates in (
            {"plan_id":"developer"},
            {"plan_monthly_price":25},
            {"plan_searches_left":9},
            {"total_searches_left":9},
            {"extra_credits":1},
            {"searches_per_month":1000},
            {"account_rate_limit_per_hour":10,"this_hour_searches":10},
            {"plan_name":"unknown"},
        ):
            with self.subTest(updates=updates):
                self.assertNotEqual(worker.free_serpapi_account_status({**free,**updates}), "free_verified")
        self.assertNotEqual(worker.free_serpapi_account_status({}), "free_verified")

    def test_google_jobs_uses_free_account_gate_and_official_detail_link(self):
        free = {
            "account_status":"Active","plan_id":"free","plan_name":"Free",
            "plan_monthly_price":0,"searches_per_month":250,
            "plan_searches_left":60,"total_searches_left":60,
            "extra_credits":0,"account_rate_limit_per_hour":50,"this_hour_searches":0
        }
        response = {"search_metadata":{"status":"Success"},
                    "jobs_results":[{"title":"Remote WordPress Developer",
                        "company_name":"Example Team",
                        "location":"Anywhere Europe",
                        "description":"Build WooCommerce storefronts",
                        "job_id":"safe-external-id",
                        "detected_extensions":{"work_from_home":True,"posted_at":"2 days ago"},
                        "apply_options":[{"link":"https://jobs.lever.co/example/123"}]}]}
        with patch.object(worker, "_serpapi_json", side_effect=[free,response]) as req:
            log, found = worker.discover_google_allowed("remote WordPress developer",0,"dummytestkey")
        self.assertEqual(req.call_count,2)
        self.assertEqual(log["status"],"serpapi_google_jobs_success")
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["url"],"https://jobs.lever.co/example/123")
        self.assertEqual(found[0]["review_status"],"unverified")
        self.assertEqual(found[0]["published_hint"],"")
        self.assertNotIn("dummytestkey",json.dumps(log)+json.dumps(found))
        with patch.object(worker, "_serpapi_json",return_value={**free,"plan_monthly_price":25}) as req:
            denied, rows=worker.discover_google_allowed("remote WordPress",0,"dummytestkey")
        self.assertEqual(req.call_count,1)
        self.assertEqual(rows,[])
        self.assertEqual(denied["status"],"not_verified_free_plan")

    def test_no_google_scraping_or_credit_spend_outside_free_slot(self):
        path=Path(__file__).resolve().parents[1]/"sources.public-snapshot.json"
        def healthy(src):
            return ({
              "source_id":src["source_id"],"url":src["base_url"],"status":"http_200",
              "checked_at":worker.utc_now(),"browser":"not_attempted",
              "candidate_count":0,"coverage":"public_response_only"
            },[])
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(worker.os.environ, {"RADAR_GOOGLE_FREE_SLOT":"false",
                                                "SERPAPI_API_KEY":"some-existing-key"}):
                with patch.object(worker,"source_check",side_effect=healthy), patch.object(
                        worker,"_serpapi_json") as api:
                    result=worker.run(path,Path(tmp)/"result.json",max_render=0,google=True)
            self.assertEqual(api.call_count,0)
            self.assertIn("free_api_not_scheduled_this_round",
                          [x["status"] for x in result["google"]])

    def test_official_remote_rss_parser_scans_beyond_first_200_xml_nodes(self):
        entries=[]
        for i in range(48):
            title="Remote WordPress Developer" if i==40 else "Warehouse Supervisor"
            entries.append("<item><title>"+title+"</title><link>https://example.com/job/"+str(i)+
                           "</link><description>Build WooCommerce storefronts</description>"+
                           "<author>Acme</author><category>Development</category>"+
                           "<pubDate>Sat, 21 Nov 2026 10:00:00 GMT</pubDate></item>")
        xml="<rss><channel>"+"".join(entries)+"</channel></rss>"
        src={**self.src,"source_id":"we-work-remotely"}
        found=worker.discover(xml,src,"https://weworkremotely.com/remote-jobs.rss")
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["location"],"Remote")
        self.assertEqual(found[0]["review_status"],"unverified")

    def test_remoteok_json_api_uses_explicit_remote_feed_provenance(self):
        data=[{"legal":"source attribution required"},
              {"position":"WordPress Developer","company":"Example",
               "url":"https://remoteok.com/remote-jobs/wordpress-developer-123",
               "location":"Worldwide","description":"Build custom WooCommerce shops"}]
        src={**self.src,"source_id":"remote-ok"}
        found=worker.discover(json.dumps(data),src,"https://remoteok.com/api?tag=dev")
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["location"],"Remote - Worldwide")

    def test_searxng_multi_engine_aggregates_only_remote_web_roles(self):
        response={
            "results":[
                {"title":"Remote WordPress Developer","url":"https://jobs.lever.co/demo/123",
                 "content":"Build WooCommerce sites. Fully remote Europe.",
                 "engines":["duckduckgo","bing"]},
                {"title":"Remote WordPress Developer","url":"https://jobs.lever.co/demo/123",
                 "content":"Fully remote worldwide.","engine":"brave"},
                {"title":"Remote WordPress Jobs","url":"https://jobs.example.com/jobs",
                 "content":"Browse remote WordPress jobs","engine":"google"},
                {"title":"WordPress Marketing Specialist Remote","url":"https://jobs.example.com/jobs/22",
                 "content":"Remote marketing","engine":"bing"},
                {"title":"Remote Elementor Developer","url":"https://jobs.example.com/jobs/23",
                 "content":"Remote US only","engine":"brave"},
                {"title":"Remote Frontend Developer","url":"http://insecure.test/1",
                 "content":"Remote","engine":"bing"},
            ],
            "unresponsive_engines":[["google","blocked"]]
        }
        with patch.object(worker,"_searxng_json",return_value=response):
            health, jobs=worker.discover_searxng("WordPress remote",0)
        self.assertEqual(health["status"],"searxng_results")
        self.assertEqual(health["blocked_engine_count"],1)
        self.assertEqual(health["candidate_count"],1)
        self.assertIn("bing",health["engines_used"])
        self.assertEqual(jobs[0]["url"],"https://jobs.lever.co/demo/123")
        self.assertEqual(jobs[0]["review_status"],"unverified")
        self.assertEqual(jobs[0]["source_id"],"google-jobs")
        self.assertEqual(jobs[0]["published_hint"],"")

    def test_searxng_does_not_register_listing_pages_or_person_profiles(self):
        titles=[
            ("WooCommerce Freelance Jobs: Work Remote & Earn Online",
             "https://www.upwork.com/freelance-jobs/woocommerce"),
            ("Remote Elementor Jobs (November 2026)",
             "https://arc.dev/remote-jobs/elementor"),
            ("Woocommerce developer jobs in Remote - Indeed",
             "https://www.indeed.com/q-woocommerce-developer-l-remote-jobs.html"),
            ("Looking for a Remote WordPress Developer Job",
             "https://www.facebook.com/groups/509617/posts/123"),
            ("Wesley Smits - Remote Freelance Front-End Developer",
             "https://nl.linkedin.com/in/example-user"),
            ("Remote Website Designer",
             "https://www.example.com/company/webstudio")
        ]
        data={"results":[{"title":title,"url":url,
                          "content":"Fully remote WordPress or Elementor work",
                          "engines":["bing"]} for title,url in titles] + [
            {"title":"Remote WordPress Developer (Europe)",
             "url":"https://jobs.lever.co/webstudio/abc123",
             "content":"Build WordPress websites, 100% remote",
             "engines":["duckduckgo"]}],"unresponsive_engines":[]}
        matches=worker._searxng_candidate_rows(data)
        self.assertEqual(len(matches),1)
        self.assertEqual(matches[0]["url"],"https://jobs.lever.co/webstudio/abc123")

    def test_searxng_errors_and_provider_blocks_not_claimed_as_empty_search(self):
        with patch.object(worker,"_searxng_json",return_value=None):
            status, found=worker.discover_searxng("WordPress remote",1)
        self.assertEqual(found,[])
        self.assertEqual(status["status"],"searxng_unavailable_or_invalid_json")
        with patch.object(worker,"_searxng_json",
                          return_value={"results":[],"unresponsive_engines":[["bing","blocked"]]}):
            status, found=worker.discover_searxng("WordPress remote",1)
        self.assertEqual(status["status"],"searxng_no_results_or_engines_blocked")
        self.assertEqual(found,[])

    def test_searxng_runs_without_paid_google_api_and_marks_all_pending(self):
        path=Path(__file__).resolve().parents[1]/"sources.public-snapshot.json"
        fake={"results":[
            {"title":"Fully Remote Elementor Designer",
             "url":"https://jobs.ashbyhq.com/demo/role123",
             "content":"Build WordPress sites, remote anywhere.",
             "engines":["duckduckgo"]}],"unresponsive_engines":[]}
        def checked(src):
            return ({"source_id":src["source_id"],"url":src["base_url"],
                     "status":"http_200","checked_at":worker.utc_now(),
                     "browser":"not_attempted","candidate_count":0,
                     "coverage":"public_response_only"},[])
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(worker.os.environ,{
                    "SEARXNG_ENABLED":"true","RADAR_GOOGLE_FREE_SLOT":"false",
                    "SERPAPI_API_KEY":"dummy-noncharged"}):
                with patch.object(worker,"source_check",side_effect=checked), patch.object(
                        worker,"_serpapi_json") as paid, patch.object(
                        worker,"_searxng_json",return_value=fake) as search:
                    result=worker.run(path,Path(tmp)/"snapshot.json",
                                      max_render=0,google=True)
            self.assertEqual(paid.call_count,0)
            self.assertEqual(search.call_count,len(worker.SEARXNG_PUBLIC_QUERIES))
            self.assertIn("searxng_results",[x["status"] for x in result["google"]])
            self.assertEqual(result["summary"]["attempted"],233)
            self.assertEqual(result["summary"]["discovered"],1)
            self.assertEqual(result["observations"][0]["review_status"],"unverified")

    def test_config_keeps_default_engines_and_json_only_on_private_loopback(self):
        text=(Path(__file__).resolve().parents[2]/"searxng"/"settings.yml").read_text(encoding="utf8")
        self.assertIn("use_default_settings: true",text)
        self.assertIn("    - json",text)
        self.assertNotIn("\nengines:",text)
        self.assertIn("limiter: false",text)
        self.assertIn("public_instance: false",text)
        self.assertEqual(worker.SEARXNG_SEARCH_ENDPOINT,
                         "http://127.0.0.1:8080/search")

    def test_browser_unavailable_is_honest(self):
        self.assertEqual(worker.render_with_chrome("https://example.com/", ""), ("browser_unavailable", ""))


if __name__ == "__main__":
    unittest.main()
