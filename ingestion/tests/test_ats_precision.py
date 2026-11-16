"""Regressions for ATS freshness, geography, and EU data residency.

These tests are offline: no network calls, credentials, or application submits.
"""
import unittest

from vacature_ingestion.adapters import ADAPTERS
from vacature_ingestion.models import SourceSpec


class ATSPrecisionTests(unittest.TestCase):
    def test_greenhouse_first_published_not_updated_timestamp(self):
        spec = SourceSpec("greenhouse", "ats", "greenhouse", "acme", "Acme")
        row = {
            "id": 123,
            "title": "WordPress Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
            "first_published": "2026-09-01T10:00:00Z",
            "updated_at": "2026-11-16T10:00:00Z",
            "location": {"name": "Europe - Remote"},
            "metadata": [{"name": "Allowed countries", "value": "Netherlands"}],
        }
        result = ADAPTERS["greenhouse"].normalize_records([row], spec)[0]
        self.assertEqual(result["published_at"], "2026-09-01T10:00:00Z")
        self.assertEqual(result["updated_at"], "2026-11-16T10:00:00Z")
        self.assertEqual(result["source_metadata"]["first_published_at"], row["first_published"])
        self.assertEqual(result["source_metadata"]["employer_metadata"], row["metadata"])

    def test_greenhouse_no_original_date_is_unknown(self):
        spec = SourceSpec("greenhouse", "ats", "greenhouse", "acme")
        row = {
            "id": 123,
            "title": "WordPress Developer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
            "updated_at": "2026-11-16T10:00:00Z",
        }
        result = ADAPTERS["greenhouse"].normalize_records([row], spec)[0]
        self.assertIsNone(result["published_at"])

    def test_ashby_hybrid_boolean_does_not_mean_fully_remote(self):
        spec = SourceSpec("ashby", "ats", "ashby", "acme")
        cases = [
            ("Hybrid", True, False),
            ("OnSite", False, False),
            ("Remote", True, True),
            (None, True, None),
        ]
        for workplace, reported, expected in cases:
            with self.subTest(workplace=workplace):
                row = {
                    "id": "role",
                    "title": "WordPress Engineer",
                    "jobUrl": "https://jobs.ashbyhq.com/acme/role",
                    "workplaceType": workplace,
                    "isRemote": reported,
                    "publishedAt": "2026-11-16T10:00:00Z",
                }
                result = ADAPTERS["ashby"].normalize_records([row], spec)[0]
                self.assertIs(result["remote"], expected)
                self.assertIs(result["source_metadata"]["reported_is_remote"], reported)
                self.assertEqual(
                    result["source_metadata"]["date_semantics"],
                    "last_published_not_original",
                )

    def test_ashby_unlisted_hidden_roles_are_excluded(self):
        spec = SourceSpec("ashby", "ats", "ashby", "acme")
        row = {
            "id": "hidden",
            "title": "WordPress Developer",
            "jobUrl": "https://jobs.ashbyhq.com/acme/hidden",
            "isListed": False,
        }
        self.assertEqual(ADAPTERS["ashby"].normalize_records([row], spec), [])

    def test_lever_eu_uses_its_own_api_host(self):
        class Client:
            def __init__(self):
                self.urls = []

            def get_json(self, url):
                self.urls.append(url)
                return [{
                    "id": "123",
                    "text": "WordPress Developer",
                    "hostedUrl": "https://jobs.eu.lever.co/acme/123",
                    "createdAt": 1730400000000,
                    "workplaceType": "remote",
                }]

        spec = SourceSpec("lever", "ats", "lever", "acme",
                          options={"api_region": "eu"})
        client = Client()
        jobs = ADAPTERS["lever"].fetch(client, spec)
        self.assertEqual(len(jobs), 1)
        self.assertTrue(client.urls[0].startswith("https://api.eu.lever.co/v0/postings/acme?"))
        result = ADAPTERS["lever"].normalize_records(jobs, spec)[0]
        self.assertIsNone(result["published_at"])
        self.assertEqual(result["source_metadata"]["provider_created_at"], 1730400000000)
        self.assertTrue(result["source_metadata"]["original_publication_unverified"])

    def test_lever_region_must_be_explicit_and_valid(self):
        class Client:
            def get_json(self, url):
                return []

        spec = SourceSpec("lever", "ats", "lever", "acme",
                          options={"api_region": "invalid"})
        with self.assertRaisesRegex(ValueError, "Lever API region"):
            ADAPTERS["lever"].fetch(Client(), spec)

    def test_lever_global_remains_default(self):
        class Client:
            def __init__(self):
                self.url = None

            def get_json(self, url):
                self.url = url
                return []

        client = Client()
        ADAPTERS["lever"].fetch(client, SourceSpec("lever", "ats", "lever", "acme"))
        self.assertTrue(client.url.startswith("https://api.lever.co/v0/postings/acme?"))


if __name__ == "__main__":
    unittest.main()
