import unittest

from vacature_ingestion.actions_readonly_bridge import read_public


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


if __name__ == "__main__":
    unittest.main()
