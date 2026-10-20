"""Offline dashboard integrity and escaping tests."""
import unittest

from scripts.render_source_coverage import render_coverage_dashboard


class CoverageDashboardTests(unittest.TestCase):
    def test_all_rows_render_with_filters_without_external_assets(self):
        data = {
            "mode": "check",
            "coverage": {
                "schema": "registered-source-coverage.v1",
                "round_index": 25,
                "google_status": "not_configured",
                "mode": "check",
                "summary": {
                    "active_total": 2, "adapter_registered": 1,
                    "google_site_eligible": 1, "google_site_planned": 1,
                    "inactive_total": 1,
                },
                "sources": [
                    {"source_id": "ashby", "source_type": "ats",
                     "registry_status": "active",
                     "coverage_route": "public_adapter",
                     "execution": "not_attempted"},
                    {"source_id": "employer-a", "source_type": "employer_direct",
                     "registry_status": "active",
                     "coverage_route": "google_site_discovery_only",
                     "execution": "google_query_planned_not_executed"},
                    {"source_id": "obsolete", "source_type": "job_board",
                     "registry_status": "retired",
                     "coverage_route": "excluded_inactive",
                     "execution": "excluded"},
                ],
            },
        }
        markup = render_coverage_dashboard(data)
        self.assertEqual(markup.count("<tr data-route="), 3)
        for term in ("employer-a", "ashby", "obsolete",
                     "Ronde: 25", "Google-query gepland",
                     "Check-modus", "Zoek bron, status of type"):
            self.assertIn(term, markup)
        self.assertIn('addEventListener("input", update)', markup)
        self.assertNotIn("https://cdn", markup)
        self.assertNotIn("fetch(", markup)

    def test_malicious_source_id_is_escaped(self):
        evil = '<img src=x onerror="alert(1)">'
        rendered = render_coverage_dashboard({
            "mode": "check",
            "coverage": {
                "schema": "registered-source-coverage.v1",
                "summary": {}, "sources": [{
                    "source_id": evil, "source_type": "job_board",
                    "registry_status": "active",
                    "coverage_route": "google_site_discovery_only",
                    "execution": "not_attempted",
                }],
            },
        })
        self.assertNotIn(evil, rendered)
        self.assertIn("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;", rendered)

    def test_missing_coverage_fails_closed(self):
        for bad in ({}, {"coverage": {}},
                    {"coverage": {"schema": "other", "sources": []}},
                    {"coverage": {"schema": "registered-source-coverage.v1"}}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    render_coverage_dashboard(bad)


if __name__ == "__main__":
    unittest.main()
