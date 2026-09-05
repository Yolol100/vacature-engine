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

    def test_personio_public_xml_and_normalization(self):
        class Client:
            def get_text(self, url, *, headers=None):
                self.url = url
                self.headers = headers
                return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
                <workzag-jobs><position>
                  <id>12345</id><subcompany>Syde</subcompany><office>100% Remote</office>
                  <department>Engineering</department><name>Senior WordPress Engineer</name>
                  <employmentType>permanent</employmentType><schedule>full-time</schedule>
                  <createdAt>2026-09-01</createdAt>
                  <jobDescriptions><jobDescription><name>About the role</name><value><![CDATA[<p>Build WordPress products.</p>]]></value></jobDescription></jobDescriptions>
                </position></workzag-jobs>"""

        spec=SourceSpec("personio","ats","personio","syde","Syde",listing_language="en",options={"language":"en"})
        client=Client()
        rows=ADAPTERS["personio"].fetch(client,spec)
        self.assertEqual(len(rows),1)
        self.assertEqual(client.url,"https://syde.jobs.personio.com/xml?language=en")
        out=ADAPTERS["personio"].normalize_records(rows,spec)[0]
        self.assertEqual(out["canonical_url"],"https://syde.jobs.personio.com/job/12345")
        self.assertEqual(out["source_job_id"],"syde:12345")
        self.assertTrue(out["remote"])
        self.assertEqual(out["listing_language"],"en")
        self.assertIn("Build WordPress products.",out["description"])

    def test_himalayas_maps_remote_restrictions_and_salary(self):
        spec=SourceSpec("himalayas","discovery_api","himalayas","global")
        row={"guid":"h1","title":"WordPress Engineer","companyName":"Acme","applicationLink":"https://himalayas.app/jobs/acme-wordpress","description":"<p>Build WordPress</p>","pubDate":"2026-09-04T00:00:00Z","expiryDate":"2026-10-04T00:00:00Z","employmentType":"Full Time","minSalary":60000,"maxSalary":80000,"currency":"EUR","salaryPeriod":"annual","locationRestrictions":[]}
        out=ADAPTERS["himalayas"].normalize_records([row],spec)[0]
        self.assertEqual(out["source_job_id"],"global:h1")
        self.assertTrue(out["remote"])
        self.assertEqual(out["location"],"Worldwide")
        self.assertEqual(out["salary"]["currency"],"EUR")

    def test_himalayas_keeps_string_location_restrictions(self):
        spec=SourceSpec("himalayas","discovery_api","himalayas","global")
        row={"guid":"h2","title":"WordPress Developer","companyName":"Acme","applicationLink":"https://himalayas.app/jobs/acme-wp","description":"WordPress","locationRestrictions":["Philippines"]}
        out=ADAPTERS["himalayas"].normalize_records([row],spec)[0]
        self.assertEqual(out["location"],"Philippines")
        self.assertEqual(out["source_metadata"]["location_restriction_names"],["Philippines"])

    def test_himalayas_keeps_object_location_restrictions(self):
        spec=SourceSpec("himalayas","discovery_api","himalayas","global")
        row={"guid":"h3","title":"WordPress Developer","companyName":"Acme","applicationLink":"https://himalayas.app/jobs/acme-wp-eu","description":"WordPress","locationRestrictions":[{"name":"Europe"}]}
        out=ADAPTERS["himalayas"].normalize_records([row],spec)[0]
        self.assertEqual(out["location"],"Europe")
        self.assertEqual(out["source_metadata"]["location_restriction_names"],["Europe"])

    def test_jobicy_maps_public_job(self):
        spec=SourceSpec("jobicy-api","discovery_api","jobicy","global")
        row={"id":9,"url":"https://jobicy.com/jobs/9","jobTitle":"WP Developer","companyName":"Acme","jobGeo":"Anywhere","jobDescription":"<p>WordPress</p>","pubDate":"2026-09-04T00:00:00Z","jobType":["full-time"]}
        out=ADAPTERS["jobicy"].normalize_records([row],spec)[0]
        self.assertEqual(out["source_job_id"],"global:9")
        self.assertEqual(out["employment_type"],"full-time")

    def test_remotive_marks_delayed_attributed_feed(self):
        spec=SourceSpec("remotive","discovery_api","remotive","global")
        row={"id":5,"url":"https://remotive.com/remote-jobs/5","title":"WP Developer","company_name":"Acme","candidate_required_location":"Worldwide","description":"<p>WordPress</p>","publication_date":"2026-09-04T00:00:00Z"}
        out=ADAPTERS["remotive"].normalize_records([row],spec)[0]
        self.assertTrue(out["source_metadata"]["attribution_required"])
        self.assertTrue(out["source_metadata"]["delayed_feed"])

if __name__ == "__main__": unittest.main()
