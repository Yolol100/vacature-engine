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
HTML='''<html lang="en"><script type="application/ld+json">{"@type":"JobPosting","title":"WordPress Developer","hiringOrganization":{"name":"Acme"},"datePosted":"2026-10-18","jobLocationType":"TELECOMMUTE","applicantLocationRequirements":{"name":"Netherlands"}}</script><body><h1>WordPress Developer</h1><p>Apply for our open engineering role.</p></body></html>'''
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
    def test_schema_without_visible_role_is_not_official_page_proof(self):
        hidden = HTML.replace("<h1>WordPress Developer</h1>", "<h1>Some other job</h1>")
        result = extract_ats_page_signals(
            hidden, title="WordPress Developer", employer="Acme", today=TODAY
        )
        self.assertIsNone(result["structured"])
        self.assertEqual(result["status"], "structured_role_not_visible_on_page")

    def test_hidden_script_or_style_title_is_not_visible_proof(self):
        no_body = HTML.replace("<h1>WordPress Developer</h1>", "")
        no_body = no_body.replace("<p>Apply", "<style>WordPress Developer</style><p>Apply")
        result = extract_ats_page_signals(
            no_body, title="WordPress Developer", employer="Acme", today=TODAY
        )
        self.assertIsNone(result["structured"])

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
        self.assertIsNone(result["application_language"])
        self.assertEqual(result["application_page_language"],"en")
        self.assertEqual(fetch.call_count,2)
    @patch("vacature_ingestion.official_page._fetch_html")
    def test_exact_application_form_requires_input_and_submit(self,fetch):
        fetch.side_effect=[
            (200,HTML),
            (200,"<html lang='en'><body><form>"
                 "<input name='email' type='email'>"
                 "<input name='resume' type='file'>"
                 "<button type='submit'>Apply</button>"
                 "</form></body></html>"),
        ]
        result=fetch_official_page_evidence(row(),active_ids={"ashby"},today=TODAY)
        self.assertTrue(result["application_form_detected"])
        self.assertIsNone(result["application_language"])
        self.assertEqual(result["application_page_language"],"en")

    @patch("vacature_ingestion.official_page._fetch_html")
    def test_200_ok_without_real_application_form_not_proof(self,fetch):
        fetch.side_effect=[
            (200,HTML),(200,"<html lang='en'><body>Applications coming soon</body></html>"),
        ]
        result=fetch_official_page_evidence(row(),active_ids={"ashby"},today=TODAY)
        self.assertEqual(result["apply_http_status"],200)
        self.assertFalse(result["application_form_detected"])

    @patch("vacature_ingestion.official_page._fetch_html")
    def test_hidden_template_form_not_application_proof(self,fetch):
        fetch.side_effect=[
            (200,HTML),(200,"<html lang='en'><template><form>"
                        "<input type='email'><input name='resume' type='file'>"
                        "<button type='submit'>Send</button>"
                        "</form></template></html>"),
        ]
        result=fetch_official_page_evidence(row(),active_ids={"ashby"},today=TODAY)
        self.assertFalse(result["application_form_detected"])

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

    @patch("vacature_ingestion.official_page._fetch_html")
    def test_embedded_application_form_is_verified_without_second_request(self,fetch):
        item={**row(),"apply_url":row()["canonical_url"]}
        form="<form><input type='email'><input type='file' name='resume'><button>Apply</button></form>"
        fetch.return_value=(200,HTML.replace("</body>",form+"</body>"))
        result=fetch_official_page_evidence(item,active_ids={"ashby"},today=TODAY)
        self.assertTrue(result["application_form_detected"])
        self.assertEqual(result["apply_http_status"],200)
        self.assertIsNone(result["application_language"])
        self.assertEqual(fetch.call_count,1)

    @patch("vacature_ingestion.official_page._fetch_html")
    def test_same_tenant_different_job_application_is_not_requested(self,fetch):
        item={**row(),"apply_url":"https://jobs.ashbyhq.com/acme/other-job/apply"}
        fetch.return_value=(200,HTML)
        result=fetch_official_page_evidence(item,active_ids={"ashby"},today=TODAY)
        self.assertEqual(result["status"],"application_route_unverified")
        self.assertFalse(result["application_form_detected"])
        self.assertEqual(fetch.call_count,1)

    @patch("vacature_ingestion.official_page._fetch_html")
    def test_newsletter_and_hidden_forms_never_prove_embedded_application(self,fetch):
        item={**row(),"apply_url":row()["canonical_url"]}
        form="<form><input type='email'><input type='file' name='resume'><button>Apply</button></form>"
        for hidden in ("<div hidden>"+form+"</div>",
                       "<div style='display: none'>"+form+"</div>",
                       "<div aria-hidden='true'>"+form+"</div>",
                       "<form><input type='email'><button>Subscribe</button></form>",
                       form.replace("<button>","<button disabled>")):
            fetch.return_value=(200,HTML.replace("</body>",hidden+"</body>"))
            result=fetch_official_page_evidence(item,active_ids={"ashby"},today=TODAY)
            self.assertFalse(result["application_form_detected"])

    def test_hidden_attributes_do_not_prove_visible_role_title(self):
        for opening in ("<div hidden>","<div style='display:none'>","<div aria-hidden='true'>"):
            html=HTML.replace("<h1>WordPress Developer</h1>",opening+"WordPress Developer</div>")
            result=extract_ats_page_signals(html,title="WordPress Developer",employer="Acme",today=TODAY)
            self.assertIsNone(result["structured"])

    @patch("vacature_ingestion.official_page._fetch_html")
    def test_hidden_candidate_inputs_never_prove_application_form(self,fetch):
        for embedded in (True,False):
            for name in ("first_name","full_name","resume","cv"):
                with self.subTest(embedded=embedded,name=name):
                    form=("<form><input type='email'>"
                          f"<input type='hidden' name='{name}'>"
                          "<button>Subscribe</button></form>")
                    item=row()
                    if embedded:
                        item["apply_url"]=item["canonical_url"]
                        fetch.side_effect=[(200,HTML.replace("</body>",form+"</body>"))]
                    else:
                        fetch.side_effect=[(200,HTML),(200,"<html lang='en'>"+form+"</html>")]
                    result=fetch_official_page_evidence(item,active_ids={"ashby"},today=TODAY)
                    self.assertFalse(result["application_form_detected"])

    @patch("vacature_ingestion.official_page._fetch_html")
    def test_disabled_fieldset_controls_never_prove_application_form(self,fetch):
        forms=(
            "<form><fieldset disabled><input type='email'><input name='first_name'>"
            "<button>Apply</button></fieldset></form>",
            "<form><input type='email'><fieldset disabled><fieldset>"
            "<input type='file' name='resume'></fieldset></fieldset><button>Apply</button></form>",
            "<form><fieldset disabled><input type='email'></fieldset>"
            "<input type='file' name='resume'><button>Apply</button></form>",
            "<form><input type='email'><input name='first_name'>"
            "<fieldset disabled><button>Apply</button></fieldset></form>",
        )
        for embedded in (True,False):
            for form in forms:
                with self.subTest(embedded=embedded,form=form):
                    item=row()
                    if embedded:
                        item["apply_url"]=item["canonical_url"]
                        fetch.side_effect=[(200,HTML.replace("</body>",form+"</body>"))]
                    else:
                        fetch.side_effect=[(200,HTML),(200,"<html lang='en'>"+form+"</html>")]
                    result=fetch_official_page_evidence(item,active_ids={"ashby"},today=TODAY)
                    self.assertFalse(result["application_form_detected"])

    @patch("vacature_ingestion.official_page._fetch_html")
    def test_separate_apply_newsletter_requires_candidate_fields(self,fetch):
        fetch.side_effect=[(200,HTML),(200,"<html lang='en'><body>Apply here"
                          "<footer><form><input type='email'>"
                          "<button>Subscribe</button></form></footer></body></html>")]
        result=fetch_official_page_evidence(row(),active_ids={"ashby"},today=TODAY)
        self.assertEqual(result["apply_http_status"],200)
        self.assertFalse(result["application_form_detected"])

    @patch("vacature_ingestion.official_page._fetch_html")
    def test_enabled_form_after_disabled_fieldset_still_proves_application(self,fetch):
        form=("<fieldset disabled><fieldset><input name='unused'></fieldset></fieldset>"
              "<form><fieldset><input type='email'><input name='full_name'>"
              "<button>Apply</button></fieldset></form>")
        for embedded in (True,False):
            with self.subTest(embedded=embedded):
                item=row()
                if embedded:
                    item["apply_url"]=item["canonical_url"]
                    fetch.side_effect=[(200,HTML.replace("</body>",form+"</body>"))]
                else:
                    fetch.side_effect=[(200,HTML),(200,"<html lang='en'>"+form+"</html>")]
                result=fetch_official_page_evidence(item,active_ids={"ashby"},today=TODAY)
                self.assertTrue(result["application_form_detected"])
if __name__=="__main__": unittest.main()
