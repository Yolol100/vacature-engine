import unittest
from vacature_ingestion.adapters import ADAPTERS
from vacature_ingestion.models import SourceSpec

class FakeClient:
    def __init__(self,pages): self.pages=pages
    def get_text(self,url,headers=None): return self.pages[url]

class JsonLdTests(unittest.TestCase):
    def test_extract_jobposting(self):
        url="https://example.test/jobs/wp"
        html='''<script type="application/ld+json">{"@type":"JobPosting","title":"WordPress Engineer","description":"<p>Build WP</p>","datePosted":"2026-09-05","jobLocationType":"TELECOMMUTE","identifier":{"value":"wp-1"},"hiringOrganization":{"name":"Acme"},"url":"https://example.test/jobs/wp?utm_source=x"}</script>'''
        spec=SourceSpec("company-acme","employer_direct","jsonld","acme",options={"urls":[url]})
        adapter=ADAPTERS["jsonld"]
        row=adapter.normalize_records(adapter.fetch(FakeClient({url:html}),spec),spec)[0]
        self.assertEqual(row["canonical_url"],"https://example.test/jobs/wp")
        self.assertTrue(row["remote"])
        self.assertEqual(row["source_job_id"],"acme:wp-1")
    def test_empty_page(self):
        url="https://example.test/careers"; spec=SourceSpec("company-acme","employer_direct","jsonld","acme",options={"urls":[url]})
        self.assertEqual(ADAPTERS["jsonld"].fetch(FakeClient({url:"<html/>"}),spec),[])

if __name__ == "__main__": unittest.main()
