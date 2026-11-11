"""Offline regression for exhaustive, explicitly requested source coverage."""
from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

from vacature_ingestion.models import SourceSpec
from vacature_ingestion.runner import SourceRunResult
from scripts.exhaustive_source_scan import _public_url, probe_unadapted_active_sources
from scripts.one_pass_vacancies import (
    RegisterPreflightError, plan_free_source_batches, run_free_discovery_batches,
    run_once,
)
from scripts.source_coverage import complete_source_coverage
from test_one_pass_vacancies import ROOT, tables


class ExhaustiveScanTests(unittest.TestCase):
    def test_visits_all_220_registered_ids_without_duplicates(self):
        active = [
            {"source_id": f"source-{i}", "status": "active",
             "source_type": "employer_direct",
             "base_url": f"https://public-{i}.example.org/jobs"}
            for i in range(220)
        ]
        recorded = []
        def probe(url):
            recorded.append(url)
            return (True, None)
        results = probe_unadapted_active_sources(
            active, {f"source-{i}" for i in range(17)}, probe=probe, max_workers=1,
        )
        self.assertEqual(len(results), 203)
        self.assertEqual(len(recorded), 203)
        self.assertEqual(len({row["registry_source_ids"][0] for row in results}), 203)
        self.assertEqual({row["attempt_kind"] for row in results},
                         {"public_landing_probe_only"})
        self.assertTrue(all(row["fetched"] == row["normalized"] == 0 for row in results))

    def test_probe_failures_are_not_zero_vacancy_evidence(self):
        active = [{"source_id": "one", "status": "active",
                   "base_url": "https://example.org/jobs"}]
        def failing(_):
            raise ConnectionError("private details must not leave probe")
        rows = probe_unadapted_active_sources(active, set(), probe=failing)
        self.assertEqual(rows[0]["failure_category"], "probe_internal_failure")
        self.assertFalse(rows[0]["success"])
        self.assertNotIn("private details", json.dumps(rows))
        for unsafe in ("http://127.0.0.1/", "http://localhost/", "file:///etc/passwd",
                       "http://user:pass@example.org/", "https://192.168.0.1/"):
            self.assertFalse(_public_url(unsafe))
        with self.assertRaises(ValueError):
            probe_unadapted_active_sources(active, set(), max_workers=100)

    def test_full_batches_do_not_stop_on_verified_target(self):
        raw = [
            {"source_id": "ashby", "source_type": "ats", "adapter": "ashby",
             "account": f"company-{i}"}
            for i in range(29)
        ]
        table = {"Bronnen": [{"source_id": "ashby", "status": "active",
                               "priority": "high", "source_type": "ats"}]}
        config = {"direct_discovery_order": "ats"}
        batches = plan_free_source_batches(
            raw, table, config, max_sources=20, exhaustive=True,
        )
        self.assertEqual(sum(len(b) for b in batches), 29)
        self.assertEqual([len(b) for b in batches], [8, 8, 8, 5])
        runner = Mock()
        def result(spec):
            return SourceRunResult(source_instance=spec.instance_id, success=True,
                                   fetched=0, normalized=0, observations=[])
        runner.run_source.side_effect = result
        out = run_free_discovery_batches(
            runner, batches, initial_observations=[],
            evaluate=lambda _: {"final_recommendations": ["already sufficient"]},
            target_verified=1, exhaustive=True,
        )
        self.assertEqual(out["fallback_sources_attempted"], 29)
        self.assertEqual(out["fallback_batches_completed"], 4)
        self.assertEqual(out["fallback_stop_reason"], "planned_sources_exhausted")
        self.assertEqual(runner.run_source.call_count, 29)

    def test_exhaustive_evaluates_only_once_after_all_batches(self):
        raw = [
            {"source_id": "ashby", "source_type": "ats", "adapter": "ashby",
             "account": "company-" + str(i)}
            for i in range(28)
        ]
        table = {"Bronnen": [{"source_id": "ashby", "status": "active",
                               "priority": "high", "source_type": "ats"}]}
        batches = plan_free_source_batches(
            raw, table, {"direct_discovery_order": "ats"},
            max_sources=20, exhaustive=True,
        )
        runner = Mock()
        runner.run_source.side_effect = lambda spec: SourceRunResult(
            source_instance=spec.instance_id, success=True,
            fetched=0, normalized=0, observations=[],
        )
        evaluator = Mock(return_value={"final_recommendations": ["already enough"]})
        report = run_free_discovery_batches(
            runner, batches, initial_observations=[], evaluate=evaluator,
            target_verified=1, exhaustive=True,
        )
        self.assertEqual(runner.run_source.call_count, 28)
        evaluator.assert_called_once()
        self.assertEqual(report["fallback_batches_completed"], 4)
        self.assertEqual(report["fallback_stop_reason"], "planned_sources_exhausted")

    def test_register_mode_is_required_and_stop_gate_fail_closed(self):
        t = tables()
        t["Config"] += [
            {"key": "vacancy_search_mode", "value": "exhaustive_all_active_sources"},
            {"key": "vacancy_search_stop_when_target_verified", "value": "TRUE"},
        ]
        with self.assertRaises(RegisterPreflightError):
            run_once(t, ROOT, "check")

    def test_run_once_full_source_ledger_does_not_claim_220_job_scans(self):
        t = tables()
        t["Config"] += [
            {"key": "vacancy_search_mode", "value": "exhaustive_all_active_sources"},
            {"key": "vacancy_search_stop_when_target_verified", "value": "FALSE"},
        ]
        t["Bronnen"] += [
            {"source_id": f"company-fake-{i}", "status": "active",
             "source_type": "employer_direct",
             "base_url": f"https://example.org/jobs/{i}", "priority": "medium"}
            for i in range(213)
        ]
        self.assertEqual(len(t["Bronnen"]), 220)
        runner = Mock()
        def fake_run(spec):
            return SourceRunResult(
                source_instance=spec.instance_id,
                registry_source_ids=(
                    [spec.source_id] +
                    ([spec.options["registry_source_id"]] if
                     isinstance(spec.options.get("registry_source_id"), str) else [])
                ),
                success=True, fetched=0, normalized=0, observations=[],
                started_at="2026-11-11T12:00:00Z",
            )
        runner.run_source.side_effect = fake_run
        def fake_probes(rows, covered):
            return [
                {"source_instance": "web:" + row["source_id"],
                 "registry_source_ids": [row["source_id"]],
                 "started_at": "2026-11-11T12:00:00Z",
                 "success": True, "fetched": 0, "normalized": 0,
                 "attempt_kind": "public_landing_probe_only",
                 "failure_category": None}
                for row in rows if row["status"] == "active"
                and row["source_id"] not in covered
            ]
        with patch("scripts.one_pass_vacancies.google_free_gate", return_value="not_configured"), \
             patch("scripts.one_pass_vacancies.IngestionRunner", return_value=runner), \
             patch("scripts.one_pass_vacancies.probe_unadapted_active_sources",
                   side_effect=fake_probes), \
             patch("scripts.one_pass_vacancies.evaluate_observations",
                   return_value={"review_candidates": [], "final_recommendations": []}):
            result = run_once(t, ROOT, "page-1")
        summary = result["source_visit_summary"]
        self.assertEqual(summary["registered_active"], 220)
        self.assertTrue(summary["all_active_sources_attempted"])
        self.assertEqual(summary["not_attempted_source_ids"], [])
        self.assertFalse(summary["listing_verified_by_landing_probes"])
        self.assertEqual(summary["attempted_source_ids"], 220)
        self.assertIn("public_landing_reachable_listing_unverified",
                      result["coverage"]["execution_counts"])
        self.assertEqual(result["fallback_stop_reason"], "planned_sources_exhausted")

    def test_exhaustive_evaluates_only_once_after_all_batches(self):
        specs = [
            SourceSpec("ashby", "ats", "ashby", f"client-{i}")
            for i in range(23)
        ]
        batches = [specs[i:i + 8] for i in range(0, len(specs), 8)]
        runner = Mock()
        runner.run_source.side_effect = lambda spec: SourceRunResult(
            source_instance=spec.instance_id,
            success=True, fetched=1, normalized=1,
            observations=[{"source_id": spec.source_id,
                           "source_instance": spec.instance_id}],
        )
        evaluate = Mock(return_value={"final_recommendations": ["matched"]})
        result = run_free_discovery_batches(
            runner, batches, initial_observations=[], evaluate=evaluate,
            target_verified=1, exhaustive=True,
        )
        self.assertEqual(runner.run_source.call_count, 23)
        evaluate.assert_called_once()
        self.assertEqual(len(evaluate.call_args.args[0]), 23)
        self.assertEqual(result["fallback_stop_reason"], "planned_sources_exhausted")

    def test_non_exhaustive_still_stops_early(self):
        specs = [
            SourceSpec("ashby", "ats", "ashby", f"client-{i}")
            for i in range(15)
        ]
        batches = [specs[i:i + 8] for i in range(0, len(specs), 8)]
        runner = Mock()
        runner.run_source.side_effect = lambda spec: SourceRunResult(
            source_instance=spec.instance_id,
            success=True, fetched=0, normalized=0, observations=[],
        )
        evaluate = Mock(return_value={"final_recommendations": ["matched"]})
        result = run_free_discovery_batches(
            runner, batches, initial_observations=[], evaluate=evaluate,
            target_verified=1, exhaustive=False,
        )
        self.assertEqual(runner.run_source.call_count, 8)
        evaluate.assert_called_once()
        self.assertEqual(result["fallback_stop_reason"], "verified_target_reached")

    def test_coverage_reports_website_probe_not_verified_role(self):
        plan = {"sources": [
            {"source_id": "one", "coverage_route": "google_site_discovery_only",
             "execution": "not_attempted"},
        ]}
        attempts = [{"registry_source_ids": ["one"], "success": True,
                     "attempt_kind": "public_landing_probe_only"}]
        result = complete_source_coverage(
            plan, google_status="not_configured",
            source_attempts=attempts, mode="page-1",
        )
        self.assertEqual(result["sources"][0]["execution"],
                         "public_landing_reachable_listing_unverified")


if __name__ == "__main__":
    unittest.main()
