from __future__ import annotations

import unittest

from vacature_ingestion.source_coverage import build_source_coverage


class SourceCoverageTests(unittest.TestCase):
    def test_every_active_source_gets_an_execution_mode(self):
        active_rows = [
            {"source_id": "remote-ok", "source_name": "Remote OK", "source_type": "job_board",
             "base_url": "https://remoteok.com/", "status": "active"},
            {"source_id": "jobgether", "source_name": "Jobgether", "source_type": "discovery",
             "base_url": "https://jobgether.com/", "status": "active"},
            {"source_id": "gmail-application-evidence", "source_name": "Gmail", "source_type": "application_evidence",
             "base_url": "", "status": "active"},
        ]
        specs = [
            {"source_id": "remote-ok", "adapter": "remoteok", "account": "global"}
        ]
        coverage = build_source_coverage(specs, active_rows)
        modes = {row["source_id"]: row["execution_mode"] for row in coverage["sources"]}
        self.assertTrue(coverage["coverage_complete"])
        self.assertEqual(modes["remote-ok"], "github_adapter")
        self.assertEqual(modes["jobgether"], "live_web_required")
        self.assertEqual(modes["gmail-application-evidence"], "mailbox_read_only")

    def test_company_binding_marks_provider_and_company_as_automated(self):
        active_rows = [
            {"source_id": "greenhouse", "source_type": "ats", "base_url": "https://boards.greenhouse.io/"},
            {"source_id": "company-acme", "source_type": "employer_direct", "base_url": "https://acme.example/jobs"},
        ]
        specs = [{
            "source_id": "greenhouse",
            "adapter": "greenhouse",
            "account": "acme",
            "options": {"registry_source_id": "company-acme"},
        }]
        coverage = build_source_coverage(specs, active_rows)
        modes = {row["source_id"]: row["execution_mode"] for row in coverage["sources"]}
        self.assertEqual(modes["greenhouse"], "github_adapter")
        self.assertEqual(modes["company-acme"], "github_adapter")
        self.assertEqual(coverage["live_web_queue_count"], 0)

    def test_missing_base_url_fails_closed(self):
        coverage = build_source_coverage(
            [],
            [{"source_id": "broken-board", "source_type": "job_board", "base_url": ""}],
        )
        self.assertFalse(coverage["coverage_complete"])
        self.assertEqual(coverage["blocked"][0]["execution_mode"], "blocked_missing_base_url")

    def test_unknown_source_type_fails_closed(self):
        coverage = build_source_coverage(
            [],
            [{"source_id": "mystery", "source_type": "mystery_type", "base_url": "https://example.test"}],
        )
        self.assertFalse(coverage["coverage_complete"])
        self.assertEqual(coverage["blocked"][0]["execution_mode"], "blocked_unknown_source_type")


if __name__ == "__main__":
    unittest.main()
