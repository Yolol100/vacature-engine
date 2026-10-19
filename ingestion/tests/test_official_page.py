import unittest
from datetime import date
from unittest.mock import patch
from vacature_ingestion.official_page import (
    _trusted_tenant_url, verified_source_account, extract_ats_page_signals,
    fetch_official_page_evidence,
)
TODAY=date(2026,10,19)
def row():
    return {"source_type":"ats","source_id":"ashby","source_instance":"ashby:acme",
      "source_metadata":{"provider":"ashby"},"canonical_url":"https://jobs.ashbyhq.com/acme/job-123",
      "apply_url":"https://jobs.ashbyhq.com/acme/job-123/apply","title":"WordPress Developer","employer":"Acme"}
HTML='''<html lang="en"><script type="application/ld+json">{"@type":"JobPosting","title":"WordPress Developer","hiringOrganization":{"name":"Acme"},"datePosted":"2026-10-18","jobLocationType":"TELECOMMUTE","applicantLocationRequirements":{"name":"Netherlands"}}</script></html>'''
class OfficialPageTests(unittest.TestCase):
    def test_account_bound_and_invalid_domain_rejected(self):
        self.assertEqual(verified_source_account(row(),active_ids={"ashby"}),("ashby","acme"))
        for url in ("https://evil.example/acme/job-123","https://jobs.ashbyhq.com/other/job-123",
                    "https://jobs.ashbyhq.com@evil.example/acme/job-123","http://jobs.ashbyhq.com/acme/job-123"):
            with self.subTest(url=url):
                self.assertFalse(_trusted_tenant_url(url,provider="ashby",account="acme"))
    def test_structured_same_employer_and_title(self):
        result=extract_ats_page_signals(HTML,title="WordPress Developer",employer="Acme",today=TODAY)
        self.assertEqual(result["status"],"matching_first_party_jobposting")
        self.assertEqual(result["structured"]["applicant_locations"],["Netherlands"])
        self.assertEqual(result["page_language"],"en")
    def test_wrong_employer_not_authoritative(self):
        result=extract_ats_page_signals(HTML,title="WordPress Developer",employer="Other",today=TODAY)
        self.assertIsNone(result["structured"])
    def test_untrusted_link_never_fetched(self):
        bad={**row(),"canonical_url":"https://evil.example/job"}
        with patch("vacature_ingestion.official_page._fetch_html") as fetch:
            result=fetch_official_page_evidence(bad,active_ids={"ashby"},today=TODAY)
        fetch.assert_not_called()
        self.assertEqual(result["status"],"unverified")
    @patch("vacature_ingestion.official_page._fetch_html")
    def test_application_language_from_separate_page(self,fetch):
        fetch.side_effect=[(200,HTML),(200,"<html lang='en'><body>Apply</body></html>")]
        result=fetch_official_page_evidence(row(),active_ids={"ashby"},today=TODAY)
        self.assertEqual(result["application_language"],"en")
        self.assertEqual(fetch.call_count,2)
    @patch("vacature_ingestion.official_page._fetch_html")
    def test_missing_separate_apply_page_remains_unknown(self,fetch):
        item={**row(),"apply_url":row()["canonical_url"]}
        fetch.return_value=(200,HTML)
        result=fetch_official_page_evidence(item,active_ids={"ashby"},today=TODAY)
        self.assertIsNone(result["application_language"])
        self.assertEqual(fetch.call_count,1)
    @patch("vacature_ingestion.official_page._fetch_html")
    def test_404_only_strong_closure(self,fetch):
        fetch.return_value=(404,None)
        result=fetch_official_page_evidence(row(),active_ids={"ashby"},today=TODAY)
        self.assertEqual(result["status"],"closed_at_exact_ats_route")
if __name__=="__main__": unittest.main()
