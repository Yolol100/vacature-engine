import json
import unittest

from vacature_engine.structured import extract_jobposting_jsonld, jobposting_facts


def script(payload):
    return f'<html><script type="application/ld+json">{json.dumps(payload)}</script></html>'


class StructuredTests(unittest.TestCase):
    def test_single_jobposting(self):
        payload = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Senior WordPress Developer",
            "datePosted": "2026-08-24",
            "jobLocationType": "TELECOMMUTE",
            "applicantLocationRequirements": {"@type": "Country", "name": "Netherlands"},
            "hiringOrganization": {"@type": "Organization", "name": "Acme"},
        }
        facts = jobposting_facts(script(payload))[0]
        self.assertTrue(facts["fully_remote_signal"])
        self.assertTrue(facts["netherlands_explicit"])
        self.assertEqual(facts["employer"], "Acme")

    def test_graph_and_type_list_supported(self):
        payload = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "Organization", "name": "Acme"},
                {"@type": ["Thing", "JobPosting"], "title": "Senior Dev"},
            ],
        }
        self.assertEqual(len(extract_jobposting_jsonld(script(payload))), 1)

    def test_array_supported(self):
        html = script([{"@type": "JobPosting", "title": "A"}, {"@type": "JobPosting", "title": "B"}])
        self.assertEqual(len(extract_jobposting_jsonld(html)), 2)

    def test_malformed_jsonld_is_ignored(self):
        html = '<script type="application/ld+json">{bad json</script>'
        self.assertEqual(extract_jobposting_jsonld(html), [])

    def test_non_job_jsonld_ignored(self):
        self.assertEqual(extract_jobposting_jsonld(script({"@type": "Article", "headline": "x"})), [])

    def test_duplicate_jobposting_is_deduplicated(self):
        posting = {"@type": "JobPosting", "title": "Same"}
        html = script([posting, posting])
        self.assertEqual(len(extract_jobposting_jsonld(html)), 1)

    def test_remote_without_applicant_location_is_not_nl_explicit(self):
        facts = jobposting_facts(script({"@type": "JobPosting", "jobLocationType": "TELECOMMUTE"}))[0]
        self.assertTrue(facts["fully_remote_signal"])
        self.assertFalse(facts["netherlands_explicit"])

    def test_nested_country_address_collected(self):
        payload = {
            "@type": "JobPosting",
            "applicantLocationRequirements": {
                "@type": "Place",
                "address": {"@type": "PostalAddress", "addressCountry": "NL"},
            },
        }
        facts = jobposting_facts(script(payload))[0]
        self.assertIn("NL", facts["applicant_locations"])
        self.assertTrue(facts["netherlands_explicit"])

    def test_job_location_collected_separately(self):
        payload = {
            "@type": "JobPosting",
            "jobLocation": {"@type": "Place", "address": {"addressCountry": "DE"}},
        }
        facts = jobposting_facts(script(payload))[0]
        self.assertIn("DE", facts["job_locations"])
        self.assertFalse(facts["netherlands_explicit"])

    def test_oversized_jsonld_block_is_ignored(self):
        huge = "x" * 1_000_100
        html = f'<script type="application/ld+json">{{"@type":"JobPosting","title":"{huge}"}}</script>'
        self.assertEqual(jobposting_facts(html), [])


if __name__ == "__main__":
    unittest.main()
