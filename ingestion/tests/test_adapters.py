import unittest

from vacature_ingestion.adapters import ADAPTERS
from vacature_ingestion.models import SourceSpec
from vacature_ingestion.normalize import normalize_canonical_url, strong_identity_keys


class AdapterTests(unittest.TestCase):
    def test_greenhouse_identity_and_date_semantics(self):
        spec = SourceSpec("greenhouse", "ats", "greenhouse", "acme", "Acme")
        row = {"id":123,"title":"Developer","location":{"name":"Remote"},"content":"<p>Hello</p>","absolute_url":"https://boards.greenhouse.io/acme/jobs/123?utm_source=x","updated_at":"2026-09-05T12:00:00Z"}
        out = ADAPTERS["greenhouse"].normalize_records([row], spec)[0]
        self.assertEqual(out["canonical_url"], "https://boards.greenhouse.io/acme/jobs/123")
        self.assertEqual(out["source_job_id"], "acme:123")
        self.assertIsNone(out["published_at"])

    def test_ashby_maps_published_remote_salary(self):
        spec = SourceSpec("ashby", "ats", "ashby", "Acme", "Acme")
        row = {"id":"abc","title":"WordPress Engineer","location":"Remote","descriptionPlain":"Build WP","publishedAt":"2026-09-01T00:00:00Z","isRemote":True,"jobUrl":"https://jobs.ashbyhq.com/Acme/abc","compensation":{"scrapeableCompensationSalarySummary":"$80K - $100K","summaryComponents":[]}}
        out = ADAPTERS["ashby"].normalize_records([row], spec)[0]
        self.assertTrue(out["remote"])
        self.assertEqual(out["salary"]["summary"], "$80K - $100K")

    def test_weak_fingerprint_not_strong_identity(self):
        row={"source_id":"board","canonical_url":"https://example.com/jobs/1","employer":"Acme","title":"Developer","location":"Remote"}
        self.assertEqual(strong_identity_keys(row), ("url:https://example.com/jobs/1",))

    def test_malformed_port_fails_closed(self):
        self.assertIsNone(normalize_canonical_url("https://example.com:abc/jobs/1"))

    def test_smartrecruiters_api_ref_not_canonical(self):
        spec=SourceSpec("smartrecruiters","ats","smartrecruiters","acme")
        row={"id":"42","name":"Developer","ref":"https://api.smartrecruiters.com/v1/companies/acme/postings/42","location":{"remote":True}}
        out=ADAPTERS["smartrecruiters"].normalize_records([row],spec)[0]
        self.assertIsNone(out["canonical_url"])
        self.assertEqual(out["source_job_id"],"acme:42")

    def test_ashby_unlisted_not_emitted(self):
        spec=SourceSpec("ashby","ats","ashby","acme")
        self.assertEqual(ADAPTERS["ashby"].normalize_records([{"id":"x","title":"Hidden","jobUrl":"https://jobs.ashbyhq.com/acme/x","isListed":False}],spec),[])

    def test_lever_remote_salary(self):
        spec=SourceSpec("lever","ats","lever","acme")
        row={"id":"x","text":"Remote Dev","hostedUrl":"https://jobs.lever.co/acme/x","categories":{"location":"Remote"},"workplaceType":"remote","salaryRange":{"currency":"EUR","min":60000,"max":80000}}
        out=ADAPTERS["lever"].normalize_records([row],spec)[0]
        self.assertTrue(out["remote"])
        self.assertEqual(out["salary"]["currency"],"EUR")

if __name__ == "__main__": unittest.main()
