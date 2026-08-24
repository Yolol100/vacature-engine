import unittest

from vacature_engine.adapters import AdapterRegistry


class FakeClient:
    def __init__(self, json_payload=None, text_payload=None):
        self.json_payload = json_payload
        self.text_payload = text_payload
        self.urls = []

    def get_json(self, url, allowed_hosts=None):
        self.urls.append(url)
        if (
            isinstance(self.json_payload, list)
            and self.json_payload
            and isinstance(self.json_payload[0], dict)
            and "content" in self.json_payload[0]
        ):
            return self.json_payload.pop(0)
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

    def test_greenhouse_normalizes(self):
        client = FakeClient(
            {
                "jobs": [
                    {
                        "id": 1,
                        "title": "Engineer",
                        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                        "location": {"name": "Remote"},
                        "content": "<p>Hello</p>",
                        "updated_at": "2026-08-24",
                    }
                ]
            }
        )
        jobs = AdapterRegistry.create("greenhouse", "acme", client=client).fetch()
        self.assertEqual(jobs[0].title, "Engineer")
        self.assertIsNone(jobs[0].posted_at)

    def test_lever_created_at_and_remote(self):
        client = FakeClient(
            [
                {
                    "id": "abc",
                    "text": "Engineer",
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

    def test_ashby_normalizes(self):
        client = FakeClient(
            {
                "jobs": [
                    {
                        "id": "1",
                        "title": "Product Engineer",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                        "applyUrl": "https://jobs.ashbyhq.com/acme/1/application",
                        "isListed": True,
                        "isRemote": True,
                        "location": "Europe",
                    }
                ]
            }
        )
        jobs = AdapterRegistry.create("ashby", "acme", client=client).fetch()
        self.assertTrue(jobs[0].is_remote)

    def test_missing_salary_stays_unknown(self):
        client = FakeClient(
            {
                "jobs": [
                    {
                        "id": "1",
                        "title": "Engineer",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                        "isListed": True,
                    }
                ]
            }
        )
        jobs = AdapterRegistry.create("ashby", "acme", client=client).fetch()
        self.assertIsNone(jobs[0].salary_summary)

    def test_personio_marks_canonical_resolution(self):
        xml = """<workzag-jobs><position><id>1</id><name>Engineer</name><office>Remote</office><department>Web</department><employmentType>permanent</employmentType><jobDescriptions><jobDescription><name>About</name><value><![CDATA[<p>Hello</p>]]></value></jobDescription></jobDescriptions></position></workzag-jobs>"""
        client = FakeClient(text_payload=xml)
        jobs = AdapterRegistry.create("personio", "acme", client=client).fetch()
        self.assertTrue(jobs[0].raw["requires_canonical_job_resolution"])


if __name__ == "__main__":
    unittest.main()
