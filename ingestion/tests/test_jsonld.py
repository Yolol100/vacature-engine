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
        self.assertEqual(row["description"],"Build WP")
        self.assertEqual(row["source_metadata"]["structured_extractor"],"extruct")
        self.assertEqual(row["source_metadata"]["text_extractor"],"trafilatura")

    def test_remote_country_requirement_uses_name(self):
        url="https://example.test/jobs/remote-us"
        html='''<script type="application/ld+json">{"@type":"JobPosting","title":"Remote WordPress Engineer","jobLocationType":"TELECOMMUTE","applicantLocationRequirements":{"@type":"Country","name":"USA"},"identifier":{"value":"wp-us"},"url":"https://example.test/jobs/remote-us"}</script>'''
        spec=SourceSpec("company-acme","employer_direct","jsonld","acme",options={"urls":[url]})
        adapter=ADAPTERS["jsonld"]
        row=adapter.normalize_records(adapter.fetch(FakeClient({url:html}),spec),spec)[0]
        self.assertEqual(row["location"],"USA")
        self.assertTrue(row["remote"])

    def test_remote_administrative_area_requirement_uses_name(self):
        url="https://example.test/jobs/remote-eu"
        html='''<script type="application/ld+json">{"@type":"JobPosting","title":"Remote WordPress Engineer","jobLocationType":"TELECOMMUTE","applicantLocationRequirements":{"@type":"AdministrativeArea","name":"European Union"},"identifier":{"value":"wp-eu"},"url":"https://example.test/jobs/remote-eu"}</script>'''
        spec=SourceSpec("company-acme","employer_direct","jsonld","acme",options={"urls":[url]})
        adapter=ADAPTERS["jsonld"]
        row=adapter.normalize_records(adapter.fetch(FakeClient({url:html}),spec),spec)[0]
        self.assertEqual(row["location"],"European Union")

    def test_remote_state_requirements_join_names(self):
        url="https://example.test/jobs/remote-states"
        html='''<script type="application/ld+json">{"@type":"JobPosting","title":"Remote WordPress Engineer","jobLocationType":"TELECOMMUTE","applicantLocationRequirements":[{"@type":"State","name":"Michigan, USA"},{"@type":"State","name":"Texas, USA"}],"identifier":{"value":"wp-states"},"url":"https://example.test/jobs/remote-states"}</script>'''
        spec=SourceSpec("company-acme","employer_direct","jsonld","acme",options={"urls":[url]})
        adapter=ADAPTERS["jsonld"]
        row=adapter.normalize_records(adapter.fetch(FakeClient({url:html}),spec),spec)[0]
        self.assertEqual(row["location"],"Michigan, USA; Texas, USA")

    def test_physical_job_location_precedes_remote_requirement(self):
        url="https://example.test/jobs/hybrid-location"
        html='''<script type="application/ld+json">{"@type":"JobPosting","title":"WordPress Engineer","jobLocationType":"TELECOMMUTE","jobLocation":{"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"Detroit","addressRegion":"MI","addressCountry":{"@type":"Country","name":"US"}}},"applicantLocationRequirements":{"@type":"Country","name":"Canada"},"identifier":{"value":"wp-hybrid"},"url":"https://example.test/jobs/hybrid-location"}</script>'''
        spec=SourceSpec("company-acme","employer_direct","jsonld","acme",options={"urls":[url]})
        adapter=ADAPTERS["jsonld"]
        row=adapter.normalize_records(adapter.fetch(FakeClient({url:html}),spec),spec)[0]
        self.assertEqual(row["location"],"Detroit, MI, US")

    def test_multiple_employment_types_are_normalized(self):
        url="https://example.test/jobs/flexible"
        html='''<script type="application/ld+json">{"@type":"JobPosting","title":"WordPress Engineer","employmentType":["FULL_TIME","CONTRACTOR"],"identifier":{"value":"wp-flex"},"url":"https://example.test/jobs/flexible"}</script>'''
        spec=SourceSpec("company-acme","employer_direct","jsonld","acme",options={"urls":[url]})
        adapter=ADAPTERS["jsonld"]
        row=adapter.normalize_records(adapter.fetch(FakeClient({url:html}),spec),spec)[0]
        self.assertEqual(row["employment_type"],"FULL_TIME; CONTRACTOR")

    def test_page_text_fallback_when_description_missing(self):
        url="https://example.test/jobs/wp"
        html='''<html><body><main><h1>WordPress Engineer</h1><p>Build accessible WordPress sites for clients.</p></main><script type="application/ld+json">{"@type":"JobPosting","title":"WordPress Engineer","identifier":{"value":"wp-2"},"hiringOrganization":{"name":"Acme"},"url":"https://example.test/jobs/wp"}</script></body></html>'''
        spec=SourceSpec("company-acme","employer_direct","jsonld","acme",options={"urls":[url]})
        adapter=ADAPTERS["jsonld"]
        row=adapter.normalize_records(adapter.fetch(FakeClient({url:html}),spec),spec)[0]
        self.assertIn("Build accessible WordPress sites",row["description"])

    def test_fallback_can_be_disabled(self):
        url="https://example.test/jobs/wp"
        html='''<html><body><main><p>Page-only text</p></main><script type="application/ld+json">{"@type":"JobPosting","title":"WordPress Engineer","identifier":{"value":"wp-3"},"url":"https://example.test/jobs/wp"}</script></body></html>'''
        spec=SourceSpec("company-acme","employer_direct","jsonld","acme",options={"urls":[url],"allow_page_text_fallback":False})
        adapter=ADAPTERS["jsonld"]
        row=adapter.normalize_records(adapter.fetch(FakeClient({url:html}),spec),spec)[0]
        self.assertIsNone(row["description"])

    def test_empty_page(self):
        url="https://example.test/careers"; spec=SourceSpec("company-acme","employer_direct","jsonld","acme",options={"urls":[url]})
        self.assertEqual(ADAPTERS["jsonld"].fetch(FakeClient({url:"<html/>"}),spec),[])

if __name__ == "__main__": unittest.main()
