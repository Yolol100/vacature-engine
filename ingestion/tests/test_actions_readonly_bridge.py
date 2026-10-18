import unittest

from vacature_ingestion.actions_readonly_bridge import read_public, read_discovery


class FakeClient:
    def __init__(self, *, jobs=None, xml=None):
        self.jobs = jobs
        self.xml = xml

    def get_json(self, url, headers=None):
        if not url.startswith("https://www.workable.com/api/accounts/awesomemotive"):
            raise AssertionError("unexpected Workable host")
        return {"jobs": self.jobs}

    def get_text(self, url, headers=None):
        if url != "https://syde.jobs.personio.com/xml?language=en":
            raise AssertionError("unexpected Personio XML URL")
        return self.xml


class ActionsReadonlyBridgeTests(unittest.TestCase):
    def test_workable_official_job_minimal_output(self):
        records = [{
            "id": "private-internal-id", "shortcode": "ABC123",
            "title": "WordPress Developer",
            "url": "https://apply.workable.com/j/ABC123/",
            "location": {"workplace_type": "remote", "country": "Netherlands"},
        }]
        result = read_public("workable", "awesomemotive", "Awesome Motive", FakeClient(jobs=records))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["identity"], "workable:awesomemotive:ABC123")
        self.assertEqual(result[0]["remote"], "remote")
        self.assertEqual(result[0]["url"], "https://apply.workable.com/awesomemotive/j/ABC123")
        self.assertNotIn("description", result[0])

    def test_workable_rejects_untrusted_job_url(self):
        bad = [{"shortcode": "ABC123", "title": "WordPress Developer",
                "url": "https://evil.example/awesomemotive/j/ABC123"}]
        with self.assertRaisesRegex(ValueError, "Invalid public ATS job data"):
            read_public("workable", "awesomemotive", "Awesome Motive", FakeClient(jobs=bad))

    def test_personio_public_xml_reuses_existing_parser(self):
        xml = "<workzag-jobs><position><id>2345</id><name>Senior WordPress Engineer</name><office>Remote</office></position></workzag-jobs>"
        result = read_public("personio", "syde", "Syde", FakeClient(xml=xml))
        self.assertEqual(result[0]["identity"], "personio:syde:2345")
        self.assertEqual(result[0]["url"], "https://syde.jobs.personio.com/job/2345")
        self.assertEqual(result[0]["remote"], "remote")

    def test_invalid_sources_and_jobs_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "Invalid public ATS source"):
            read_public("personio", "../test", "Syde", FakeClient(xml=""))
        with self.assertRaisesRegex(ValueError, "Invalid public ATS job"):
            read_public("workable", "awesomemotive", "Awesome Motive", FakeClient(jobs=[{"id": "01", "title": "Role", "url": "https://apply.workable.com/awesomemotive/j/01"}]))
        with self.assertRaisesRegex(ValueError, "Invalid public ATS job data"):
            read_public("personio", "syde", "Syde", FakeClient(xml="<jobs><position><id>123</id><name>" + "X"*300 + "</name></position></jobs>"))



class DiscoveryClient:
    def __init__(self):
        self.calls = []

    def get_json(self, url, headers=None):
        self.calls.append(url)
        if "jobicy.com/api/v2/remote-jobs" in url:
            return {"jobs": [{"id": 400, "jobTitle": "Remote WordPress Developer",
                              "url": "https://jobicy.com/jobs/400", "companyName": "Example",
                              "jobGeo": "Europe"}]}
        if "remotive.com/api/remote-jobs" in url:
            return {"jobs": [{"id": 401, "title": "Remote WordPress Developer",
                              "url": "https://remotive.com/remote-jobs/software-dev/401",
                              "company_name": "Example", "candidate_required_location": "Europe"}]}
        if "remoteok.com/api" in url:
            return [{"legal": "terms"}, {"id": "402", "position": "Remote WordPress Developer",
                    "url": "https://remoteok.com/remote-jobs/402", "company": "Example",
                    "location": "Worldwide"}]
        if "himalayas.app/jobs/api/search" in url:
            if "page=2" in url:
                return {"jobs": []}
            return {"jobs": [{"guid": "403", "title": "Remote WordPress Developer",
                    "applicationLink": "https://himalayas.app/jobs/403",
                    "companyName": "Example", "locationRestrictions": []}]}
        if url == "https://www.arbeitnow.com/api/job-board-api":
            return {"data": [{"slug": "wordpress-dev", "title": "Remote WordPress Developer",
                 "company_name": "Example", "url": "https://www.arbeitnow.com/jobs/wordpress-dev",
                 "remote": True, "location": "Europe"}]}
        if url.startswith("https://remotelanders.com/api/jobs?"):
            return {"jobs": ([{"slug": "wordpress-dev", "title": "Remote WordPress Developer",
                  "company": "Example", "url": "https://remotelanders.com/jobs/wordpress-dev",
                  "location": "Europe"}] if "Engineering" in url else [])}
        if url.startswith("https://remotejobs.org/api/v1/jobs?"):
            return {"data": ([{"id": "wordpress-dev", "title": "Remote WordPress Developer",
                     "company": {"name": "Example"}, "location": "Europe",
                     "url": "https://remotejobs.org/remote-jobs/wordpress-dev"}]
                    if "wordpress" in url else []), "pagination": {"has_more": False}}
        raise AssertionError("Unexpected discovery API URL")

    def get_text(self, url, headers=None):
        self.calls.append(url)
        if url == "https://weworkremotely.com/categories/remote-programming-jobs.rss":
            return "<rss><channel><item><title>Example: Remote WordPress Developer</title><link>https://weworkremotely.com/remote-jobs/example-wordpress-404</link><guid>404</guid><description>WordPress engineer</description></item></channel></rss>"
        raise AssertionError("Unexpected discovery RSS URL")


class ReadonlyDiscoveryBridgeTests(unittest.TestCase):
    def test_existing_eight_feeds_are_bounded_and_discovery_only(self):
        for provider in ("remotive", "jobicy-api", "himalayas", "we-work-remotely", "remote-ok",
                         "remote-landers-api", "remotejobs-org", "arbeitnow-api"):
            with self.subTest(provider=provider):
                client = DiscoveryClient()
                response = read_discovery(provider, client)
                rows = response["jobs"]
                self.assertEqual(response["quarantined"], 0)
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertEqual(row["source_id"], provider)
                self.assertTrue(row["url"].startswith("https://"))
                self.assertIn("WordPress", row["title"])
                self.assertNotIn("verified", row)
                self.assertNotIn("description", row)
                self.assertEqual(len(row["source_job_id"]), 24)
                self.assertLessEqual(len(client.calls), 2)

    def test_arbeitnow_quarantines_untrusted_only_and_reports_partial(self):
        class Mixed(DiscoveryClient):
            def get_json(self, url, headers=None):
                return {"data": [
                    {"slug": "valid", "title": "Remote WordPress Developer",
                     "company_name": "Example", "remote": True,
                     "url": "https://www.arbeitnow.com/jobs/valid"},
                    {"slug": "unsafe", "title": "Remote WordPress Developer",
                     "company_name": "Example", "remote": True,
                     "url": "https://malicious.example/collect?token=secret"},
                ]}
        result = read_discovery("arbeitnow-api", Mixed())
        self.assertEqual(result["quarantined"], 1)
        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["url"], "https://www.arbeitnow.com/jobs/valid")
        self.assertNotIn("malicious.example", str(result))

    def test_arbeitnow_malformed_authority_quarantines_only_the_bad_record(self):
        class Malformed(DiscoveryClient):
            def get_json(self, url, headers=None):
                self.asserted_url = url
                return {"data": [
                    {"slug": "good", "title": "Remote WordPress Developer",
                     "company_name": "Example", "remote": True,
                     "url": "https://www.arbeitnow.com/jobs/good"},
                    {"slug": "bad", "title": "Remote WordPress Developer",
                     "company_name": "Example", "remote": True,
                     "url": "https://[bad"},
                ]}
        result = read_discovery("arbeitnow-api", Malformed())
        self.assertEqual(result["quarantined"], 1)
        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["url"], "https://www.arbeitnow.com/jobs/good")
        self.assertNotIn("[bad", str(result))

    def test_malformed_authority_on_other_feed_still_fails_closed(self):
        class Invalid(DiscoveryClient):
            def get_json(self, url, headers=None):
                return {"data": [{"id": "bad", "title": "Remote WordPress Developer",
                                  "url": "https://[bad"}]}
        with self.assertRaisesRegex(ValueError, "Unexpected public feed job URL: malformed"):
            read_discovery("remotejobs-org", Invalid())

    def test_non_arbeitnow_bad_link_fails_closed(self):
        class Invalid(DiscoveryClient):
            def get_json(self, url, headers=None):
                return {"data": [{"id": "x", "title": "Remote role",
                                  "url": "https://evil.example/job"}]}
        with self.assertRaisesRegex(ValueError, "Unexpected public feed job URL"):
            read_discovery("remotejobs-org", Invalid())

    def test_discovery_unknown_source_cannot_access_arbitrary_host(self):
        client = DiscoveryClient()
        with self.assertRaisesRegex(ValueError, "Unsupported discovery source"):
            read_discovery("../../secrets", client)
        self.assertEqual(client.calls, [])

    def test_discovery_rejects_untrusted_canonical_url(self):
        class BadClient(DiscoveryClient):
            def get_json(self, url, headers=None):
                return {"jobs": [{"id": 123, "title": "WordPress Developer",
                                  "url": "http://localhost/secret",
                                  "company_name": "Unknown"}]}
        with self.assertRaisesRegex(ValueError, "Invalid public discovery role"):
            read_discovery("remotive", BadClient())


class SafeBridgeDiagnosticsTests(unittest.TestCase):
    def test_only_bounded_categories_reach_stderr(self):
        import io
        import sys
        from contextlib import redirect_stderr
        from unittest.mock import patch
        from vacature_ingestion import actions_readonly_bridge as bridge
        from vacature_ingestion.http import FetchError

        cases = [
            (FetchError("timeout_or_network", "https://private.example/?token=secret"),
             "public_ats_fetch_timeout_or_network"),
            (FetchError("blocked_or_auth_required", "secret", status=403),
             "public_ats_http_403"),
            (ValueError("secret provider response"), "public_ats_contract_other"),
            (ValueError("Invalid Arbeitnow response"), "public_ats_contract_schema"),
            (ValueError("Unexpected public feed job URL"), "public_ats_contract_job_url"),
            (ValueError("Unexpected public feed job URL: malformed"), "public_ats_contract_job_url_malformed"),
            (ValueError("Unexpected public feed job URL: uk_apex"), "public_ats_contract_job_url_uk_apex"),
            (ValueError("Unexpected public feed job URL: untrusted_host"), "public_ats_contract_job_url_untrusted_host"),
            (ValueError("Invalid public discovery role"), "public_ats_contract_normalized_role"),
            (TypeError("private token"), "public_ats_internal_error"),
        ]
        for err, expected in cases:
            with (self.subTest(expected=expected),
                  patch.object(sys, "argv", ["radar", "--discovery", "arbeitnow-api"]),
                  patch.object(bridge, "read_discovery", side_effect=err)):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    self.assertEqual(bridge.main(), 1)
                self.assertEqual(stderr.getvalue().strip(), expected)


if __name__ == "__main__":
    unittest.main()
