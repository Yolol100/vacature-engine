"""Focused evidence-only Bronnen proposal regressions (no credentials/network)."""
import json
import unittest
from datetime import datetime, timezone

from scripts.source_health_handoff import source_health_handoff

NOW = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)
STAMP = "2026-10-20T13:00:00Z"


def fixtures():
    rows = [
        {"source_id": "ats", "status": "active", "last_success_at": "",
         "last_failure_at": "", "consecutive_failures": "0", "failure_category": ""},
        {"source_id": "company-a", "status": "active", "last_success_at": "",
         "last_failure_at": "", "consecutive_failures": "2", "failure_category": ""},
        {"source_id": "google-jobs", "status": "active", "last_success_at": "",
         "last_failure_at": "", "consecutive_failures": "0", "failure_category": ""},
        {"source_id": "source-google-only", "status": "active", "last_success_at": "",
         "last_failure_at": "", "consecutive_failures": "0", "failure_category": ""},
        {"source_id": "retired", "status": "retired", "last_success_at": "",
         "last_failure_at": "", "consecutive_failures": "0", "failure_category": ""},
    ]
    coverage = {"sources": [
        {"source_id": "ats", "coverage_route": "public_adapter"},
        {"source_id": "company-a", "coverage_route": "public_adapter"},
        {"source_id": "google-jobs", "coverage_route": "free_google_optional"},
        {"source_id": "source-google-only",
         "coverage_route": "google_site_discovery_only"},
        {"source_id": "retired", "coverage_route": "excluded_inactive"},
    ]}
    return rows, coverage


def attempt(ids, success, *, timestamp=STAMP, category=None, normalized=0):
    return {"source_instance": "ats:tenant", "registry_source_ids": ids,
            "success": success, "started_at": timestamp, "normalized": normalized,
            "failure_category": category, "untrusted_raw_error": "PRIVATE TOKEN 12345"}


class SourceHealthHandoffTests(unittest.TestCase):
    def make(self, events):
        return source_health_handoff(*fixtures(), events, asof=NOW)

    def test_never_backfills_unknown_sources_from_plans(self):
        result = self.make([])
        self.assertEqual(result["registry_active_sources_without_health_time"], 4)
        self.assertEqual(result["proposals"], [])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["auto_write"])

    def test_exact_provider_and_employer_attempt_success(self):
        result = self.make([attempt(["ats", "company-a"], True, normalized=7)])
        self.assertEqual(result["proposed_source_count"], 2)
        by_id = {x["source_id"]: x for x in result["proposals"]}
        self.assertEqual(by_id["company-a"]["expected"]["last_success_at"], "")
        self.assertEqual(by_id["company-a"]["proposed"]["last_success_at"], STAMP)
        self.assertEqual(by_id["company-a"]["proposed"]["consecutive_failures"], "0")
        self.assertNotIn("last_result_count", by_id["company-a"]["proposed"])
        self.assertNotIn("status", by_id["company-a"]["proposed"])

    def test_failure_updates_only_evidenced_fields_with_safe_category(self):
        result = self.make([attempt(["company-a"], False, category="rate_limited")])
        update = result["proposals"][0]["proposed"]
        self.assertEqual(update["last_failure_at"], STAMP)
        self.assertEqual(update["consecutive_failures"], "3")
        self.assertEqual(update["failure_category"], "rate_limited")
        self.assertNotIn("next_retry_at", update)

    def test_google_site_discovery_is_not_direct_source_health(self):
        result = self.make([attempt(["source-google-only"], True)])
        self.assertEqual(result["proposals"], [])
        self.assertEqual(result["registry_active_sources_without_health_time"], 4)

    def test_one_google_batch_only_updates_google_provider_not_sites(self):
        result = self.make([attempt(["google-jobs", "source-google-only"], True)])
        self.assertEqual([x["source_id"] for x in result["proposals"]], ["google-jobs"])
        self.assertEqual(result["proposals"][0]["kind"],
                         "verified_free_google_provider_attempt")

    def test_mixed_tenants_never_claim_all_success_or_all_failure(self):
        result = self.make([attempt(["ats"], True),
                            attempt(["ats"], False, category="rate_limited")])
        self.assertEqual(result["mixed_source_skipped"], 1)
        self.assertEqual(result["proposals"], [])

    def test_older_attempt_does_not_override_newer_register_health(self):
        rows, plan = fixtures()
        rows[0]["last_success_at"] = "2026-10-20T13:15:00Z"
        result = source_health_handoff(
            rows, plan, [attempt(["ats"], True)], asof=NOW)
        self.assertEqual(result["stale_source_skipped"], 1)
        self.assertEqual(result["proposals"], [])

    def test_older_success_does_not_reset_a_newer_failure(self):
        rows, plan = fixtures()
        rows[0]["last_failure_at"] = "2026-10-20T13:15:00Z"
        rows[0]["consecutive_failures"] = "3"
        result = source_health_handoff(
            rows, plan, [attempt(["ats"], True)], asof=NOW)
        self.assertEqual(result["stale_source_skipped"], 1)
        self.assertEqual(result["proposals"], [])

    def test_future_or_unstamped_events_cannot_invent_health(self):
        result = self.make([attempt(["ats"], True, timestamp=None),
                            attempt(["ats"], True, timestamp="2026-10-21T13:00:00Z"),
                            attempt(["ats"], True, timestamp="yesterday")])
        self.assertEqual(result["proposals"], [])
        self.assertEqual(result["invalid_attempt_skipped"], 3)

    def test_non_bool_outcome_and_malformed_count_rejected(self):
        result = self.make([dict(attempt(["ats"], True), success="TRUE"),
                            attempt(["ats"], True, normalized=-1)])
        self.assertEqual(result["proposals"], [])
        self.assertEqual(result["invalid_attempt_skipped"], 2)

    def test_retired_sources_not_reactivated(self):
        result = self.make([attempt(["retired"], True)])
        self.assertEqual(result["proposals"], [])

    def test_untrusted_exception_or_sensitive_claims_never_exported(self):
        result = self.make([attempt(["company-a"], False,
                                    category="TOKEN_SECRET_IN_PROVIDER_ERROR")])
        encoded = json.dumps(result)
        self.assertNotIn("PRIVATE TOKEN", encoded)
        self.assertNotIn("TOKEN_SECRET_IN_PROVIDER_ERROR", encoded)
        self.assertEqual(result["proposals"][0]["proposed"]["consecutive_failures"], "3")
        self.assertNotIn("failure_category", result["proposals"][0]["proposed"])

    def test_duplicate_registry_ids_fail_closed(self):
        rows, coverage = fixtures()
        rows.append(dict(rows[0]))
        with self.assertRaises(ValueError):
            source_health_handoff(rows, coverage, [], asof=NOW)


if __name__ == "__main__":
    unittest.main()
