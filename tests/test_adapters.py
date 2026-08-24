import unittest

from vacature_engine.adapters import AdapterRegistry


class FakeClient:
    def __init__(self, json_payload=None, text_payload=None, routes=None):
        self.json_payload = json_payload
        self.text_payload = text_payload
        self.routes = routes or {}
        self.urls = []

    def get_json(self, url, allowed_hosts=None):
        self.urls.append(url)
        for needle, value in self.routes.items():
            if needle in url:
                return value() if callable(value) else value
        if isinstance(self.json_payload, list) and self.json_payload and isinstance(self.json_payload[0], tuple):
            return self.json_payload.pop(0)[1]
        return self.json_payload

    def get_text(self, url, allowed_hosts=None):
        self.urls.append(url)
        return self.text_payload


class AdapterTests(unittest.TestCase):
    def test_registry_has_public_read_adapters(self):
        self.assertEqual(
            AdapterRegistry.available(),
            ["ashby", "greenhouse", "lever", "personio", "smartrecruiters"],
        )

    def test_greenhouse_uses_first_published_and_skips_prospect(self):
        client = FakeClient(
            {
                "jobs": [
                    {
                        "id": 1,
                        "internal_job_id": 9,
                        "title": "Senior Engineer",
                        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                        "location": {"name": "Remote"},
                        "content": "<p>Hello</p>",
                        "first_published": "2026-08-24T10:00:00Z",
                        "updated_at": "2026-08-25T10:00:00Z",
                    },
                    {
                        "id": 2,
                        "internal_job_id": None,
                        "title": "Join our talent network",
                        "absolute_url": "https://boards.greenhouse.io/acme/jobs/2",
                    },
                ]
            }
        )
        jobs = AdapterRegistry.create("greenhouse", "acme", client=client).fetch()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].posted_at, "2026-08-24T10:00:00Z")
        self.assertEqual(jobs[0].source_date_semantics, "updated_at")

    def test_lever_created_at_and_remote(self):
        client = FakeClient(
            [
                {
                    "id": "abc",
                    "text": "Senior Engineer",
                    "hostedUrl": "https://jobs.lever.co/acme/abc",
                    "applyUrl": "https://jobs.lever.co/acme/abc/apply",
                    "createdAt": 1787616000000,
                    "workplaceType": "remote",
                    "categories": {"location": "Remote", "team": "Platform"},
                }
            ]
        )
        jobs = AdapterRegistry.create("lever", "acme", client=client).fetch()
        self.assertTrue(jobs[0].is_remote)
        self.assertIsNotNone(jobs[0].posted_at)

    def test_lever_hybrid_never_upgraded_by_remote_location_text(self):
        client = FakeClient(
            [
                {
                    "id": "abc",
                    "text": "Senior Engineer",
                    "hostedUrl": "https://jobs.lever.co/acme/abc",
                    "workplaceType": "hybrid",
                    "categories": {"location": "Remote / London"},
                }
            ]
        )
        job = AdapterRegistry.create("lever", "acme", client=client).fetch()[0]
        self.assertFalse(job.is_remote)

    def test_ashby_last_published_is_not_original_freshness(self):
        client = FakeClient(
            {
                "jobs": [
                    {
                        "id": "1",
                        "title": "Senior Product Engineer",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                        "isListed": True,
                        "isRemote": True,
                        "workplaceType": "Remote",
                        "publishedAt": "2026-08-25T00:00:00Z",
                    }
                ]
            }
        )
        job = AdapterRegistry.create("ashby", "acme", client=client).fetch()[0]
        self.assertIsNone(job.posted_at)
        self.assertEqual(job.source_date_semantics, "last_published")

    def test_ashby_hybrid_is_not_fully_remote_even_if_is_remote_true(self):
        client = FakeClient(
            {
                "jobs": [
                    {
                        "id": "1",
                        "title": "Senior Engineer",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                        "isListed": True,
                        "isRemote": True,
                        "workplaceType": "Hybrid",
                    }
                ]
            }
        )
        self.assertFalse(AdapterRegistry.create("ashby", "acme", client=client).fetch()[0].is_remote)

    def test_missing_salary_stays_unknown(self):
        client = FakeClient(
            {"jobs": [{"id": "1", "title": "Senior Engineer", "jobUrl": "https://jobs.ashbyhq.com/acme/1", "isListed": True}]}
        )
        jobs = AdapterRegistry.create("ashby", "acme", client=client).fetch()
        self.assertIsNone(jobs[0].salary_summary)

    def test_personio_uses_current_dot_com_and_direct_job_url(self):
        xml = """<workzag-jobs><position><id>123</id><name>Senior Engineer</name><office>Remote</office><department>Web</department><employmentType>permanent</employmentType><jobDescriptions><jobDescription><name>About</name><value><![CDATA[<p>Hello</p>]]></value></jobDescription></jobDescriptions></position></workzag-jobs>"""
        client = FakeClient(text_payload=xml)
        job = AdapterRegistry.create("personio", "acme", client=client).fetch()[0]
        self.assertEqual(client.urls[0], "https://acme.jobs.personio.com/xml?language=en")
        self.assertEqual(job.job_url, "https://acme.jobs.personio.com/job/123")
        self.assertFalse(job.raw["requires_canonical_job_resolution"])

    def test_personio_invalid_subdomain_slug_rejected(self):
        for slug in ("evil.com/path", "bad slug", "-bad", "bad-"):
            with self.subTest(slug=slug), self.assertRaises(ValueError):
                AdapterRegistry.create("personio", slug, client=FakeClient(text_payload="<x/>"))

    def test_smartrecruiters_prefers_posting_url_and_keeps_release_discovery_only(self):
        listing = {
            "content": [{"id": "1", "name": "Senior Engineer", "releasedDate": "2026-08-24T00:00:00Z"}],
            "totalFound": 1,
        }
        detail = {
            "id": "1",
            "name": "Senior Engineer",
            "postingUrl": "https://jobs.smartrecruiters.com/Acme/1",
            "applyUrl": "https://jobs.smartrecruiters.com/Acme/1/apply",
            "releasedDate": "2026-08-24T00:00:00Z",
            "location": {"country": "nl", "remote": True},
        }
        client = FakeClient(routes={"?destination=PUBLIC": listing, "/postings/1": detail})
        job = AdapterRegistry.create("smartrecruiters", "acme", client=client).fetch()[0]
        self.assertEqual(job.job_url, "https://jobs.smartrecruiters.com/Acme/1")
        self.assertIsNone(job.posted_at)
        self.assertEqual(job.source_date_semantics, "released_date_not_proven_original")

    def test_smartrecruiters_paginates_until_total(self):
        page1 = {"content": [{"id": str(i)} for i in range(100)], "totalFound": 101}
        page2 = {"content": [{"id": "100"}], "totalFound": 101}
        client = FakeClient(routes={"offset=0": page1, "offset=100": page2})
        adapter = AdapterRegistry.create("smartrecruiters", "acme", client=client)
        items = adapter._list_postings("https://api.smartrecruiters.com/v1/companies/acme/postings")
        self.assertEqual(len(items), 101)
        self.assertTrue(any("offset=100" in url for url in client.urls))


if __name__ == "__main__":
    unittest.main()
