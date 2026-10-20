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

    def test_structured_remote_hiring_area_overrides_physical_office(self):
        import json
        url = "https://example.test/jobs/wordpress"
        common = {
            "@type": "JobPosting",
            "title": "WordPress Developer",
            "url": url,
            "identifier": {"value": "wp-remote"},
            "jobLocationType": "TELECOMMUTE",
        }
        office = {"@type": "Place", "address": {
            "@type": "PostalAddress",
            "addressLocality": "Detroit", "addressRegion": "MI",
            "addressCountry": {"@type": "Country", "name": "USA"},
        }}
        cases = [
            ("country", {"applicantLocationRequirements": {
                "@type": "Country", "name": "USA"}}, "USA"),
            ("remote_eligible_eu_with_us_office", {
                "jobLocation": office,
                "applicantLocationRequirements": {
                    "@type": "AdministrativeArea", "name": "European Union"},
            }, "European Union"),
            ("remote_restricted_us_with_eu_office", {
                "jobLocation": {"@type": "Place", "address": {
                    "addressLocality": "Utrecht",
                    "addressCountry": {"@type": "Country", "name": "Netherlands"}}},
                "applicantLocationRequirements": {
                    "@type": "Country", "name": "USA"},
            }, "USA"),
            ("multiple_countries", {"applicantLocationRequirements": [
                {"@type": "Country", "name": "USA"},
                {"@type": "Country", "name": "Canada"},
            ]}, "USA; Canada"),
            ("physical_location_fallback", {
                "jobLocation": office,
            }, "Detroit, MI, USA"),
        ]
        spec = SourceSpec(
            "company-acme", "employer_direct", "jsonld", "acme",
            options={"urls": [url]})
        for label, fields, location in cases:
            with self.subTest(label=label):
                payload = {**common, **fields}
                html = ("<script type='application/ld+json'>"
                        + json.dumps(payload) + "</script>")
                obs = ADAPTERS["jsonld"].normalize_records(
                    ADAPTERS["jsonld"].fetch(FakeClient({url: html}), spec),
                    spec)[0]
                self.assertEqual(obs["location"], location)
                self.assertEqual(obs["remote"], True)
                self.assertNotIn("'@type':", obs["location"])
                self.assertEqual(obs["source_metadata"][
                    "applicant_location_requirements"],
                    payload.get("applicantLocationRequirements"))

    def test_multiple_employment_types_do_not_leak_python_list_syntax(self):
        import json
        url = "https://example.test/jobs/wordpress"
        payload = {
            "@type": "JobPosting", "title": "WordPress Developer",
            "url": url, "identifier": {"value": "wp-types"},
            "employmentType": ["FULL_TIME", "CONTRACTOR"],
        }
        html = ("<script type='application/ld+json'>"
                + json.dumps(payload) + "</script>")
        spec = SourceSpec("company-acme", "employer_direct", "jsonld", "acme",
                          options={"urls": [url]})
        obs = ADAPTERS["jsonld"].normalize_records(
            ADAPTERS["jsonld"].fetch(FakeClient({url: html}), spec), spec)[0]
        self.assertEqual(obs["employment_type"], "FULL_TIME; CONTRACTOR")

    def test_empty_page(self):
        url="https://example.test/careers"; spec=SourceSpec("company-acme","employer_direct","jsonld","acme",options={"urls":[url]})
        self.assertEqual(ADAPTERS["jsonld"].fetch(FakeClient({url:"<html/>"}),spec),[])

if __name__ == "__main__": unittest.main()
