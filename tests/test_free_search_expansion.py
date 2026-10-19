"""Bounded free discovery: no live requests, score fabrication or Register writes."""
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.one_pass_vacancies import (
    main, plan_free_source_batches, run_free_discovery_batches, run_once,
    select_free_specs,
)
from vacature_ingestion.models import SourceSpec
from vacature_ingestion.runner import IngestionRunner, SourceRunResult


CONFIG = {
    "direct_discovery_order": "ats,discovery_api,job_board,discovery",
    "high_source_order": "ashby,we-work-remotely,remote-ok",
}


def source_row(source_id, source_type="ats", status="active", priority="high"):
    return {"source_id": source_id, "source_type": source_type,
            "status": status, "priority": priority}


def specs(count):
    return [{"source_id": "ashby", "source_type": "ats", "adapter": "ashby",
             "account": "employer-" + str(i), "max_jobs": 20_000}
            for i in range(count)]


def registry(*extra):
    return {"Bronnen": [source_row("ashby"), *extra]}


class FakeRunner:
    def __init__(self, failed=()):
        self.calls = []
        self.failed = set(failed)

    def run_source(self, source):
        self.calls.append(source.instance_id)
        ok = source.instance_id not in self.failed
        return SourceRunResult(
            source_instance=source.instance_id, success=ok,
            fetched=1 if ok else 0, normalized=1 if ok else 0,
            # A stale payload on a failed request must never enter evaluation.
            observations=[{"source_instance": source.instance_id,
                           "canonical_url": "https://jobs.ashbyhq.com/"
                                            + source.account + "/role"}],
        )


def pending(rows):
    return {"review_candidates": rows, "final_recommendations": []}


class FreeSearchExpansionTests(unittest.TestCase):
    def test_later_employer_is_reached_despite_full_unverified_review_queue(self):
        batches = plan_free_source_batches(specs(10), registry(), CONFIG,
                                           max_sources=10)
        runner = FakeRunner()
        evaluations = []

        def evaluate(rows):
            evaluations.append(len(rows))
            # The existing ranking engine is injected here. Only its verified
            # result controls continuation; a large review queue is irrelevant.
            final = [row for row in rows
                     if row["source_instance"] == "ashby:employer-9"]
            return {"review_candidates": rows, "final_recommendations": final}

        result = run_free_discovery_batches(
            runner, batches, initial_observations=[], evaluate=evaluate,
            target_verified=1,
        )
        self.assertEqual(evaluations, [8, 10])
        self.assertEqual(result["fallback_batches_completed"], 2)
        self.assertEqual(result["fallback_sources_attempted"], 10)
        self.assertEqual(result["fallback_stop_reason"], "verified_target_reached")
        self.assertEqual(result["evaluation"]["final_recommendations"][0]
                         ["source_instance"], "ashby:employer-9")

    def test_stops_at_live_output_target_before_fetching_more_sources(self):
        runner = FakeRunner()
        batches = plan_free_source_batches(specs(25), registry(), CONFIG,
                                           max_sources=20)
        result = run_free_discovery_batches(
            runner, batches, initial_observations=[],
            evaluate=lambda rows: {"final_recommendations": rows[:2]},
            target_verified=2,
        )
        self.assertEqual(len(runner.calls), 8)
        self.assertEqual(result["fallback_batches_completed"], 1)
        self.assertEqual(result["fallback_stop_reason"], "verified_target_reached")

    def test_total_budget_covers_multiple_batches_without_repeating_sources(self):
        batches = plan_free_source_batches(specs(30), registry(), CONFIG,
                                           max_sources=20)
        self.assertEqual([len(batch) for batch in batches], [8, 8, 4])
        flat = [spec for batch in batches for spec in batch]
        self.assertEqual(len({spec.instance_id for spec in flat}), 20)
        self.assertTrue(all(spec.max_jobs == 80 for spec in flat))
        self.assertTrue(all(spec.timeout_seconds == 12.0 and spec.retries == 1
                            for spec in flat))
        runner = FakeRunner()
        result = run_free_discovery_batches(
            runner, batches, initial_observations=[], evaluate=pending,
            target_verified=5,
        )
        self.assertEqual(result["fallback_sources_attempted"], 20)
        self.assertEqual(result["fallback_batches_completed"], 3)
        self.assertEqual(result["fallback_stop_reason"], "planned_sources_exhausted")
        self.assertEqual(runner.calls[-1], "ashby:employer-19")

    def test_explicit_small_total_budget_is_never_expanded(self):
        batches = plan_free_source_batches(specs(12), registry(), CONFIG,
                                           max_sources=3)
        self.assertEqual([len(batch) for batch in batches], [3])
        runner = FakeRunner()
        run_free_discovery_batches(runner, batches, initial_observations=[],
                                   evaluate=pending, target_verified=5)
        self.assertEqual(len(runner.calls), 3)

    def test_duplicate_specs_preserve_first_curated_position(self):
        raw = specs(3)
        raw.append(dict(raw[0]))
        batches = plan_free_source_batches(raw, registry(), CONFIG,
                                           max_sources=8, batch_size=2)
        self.assertEqual([[spec.instance_id for spec in batch] for batch in batches],
                         [["ashby:employer-0", "ashby:employer-1"],
                          ["ashby:employer-2"]])

    def test_malformed_retired_spec_cannot_block_active_free_sources(self):
        raw = [{"source_id": "retired-provider", "account": "bad-old-spec"},
               *specs(2)]
        tables = registry(source_row("retired-provider", status="retired"))
        selected = select_free_specs(raw, tables, CONFIG, limit=3)
        self.assertEqual([spec.instance_id for spec in selected],
                         ["ashby:employer-0", "ashby:employer-1"])

    def test_company_and_provider_retirement_still_gate_later_batches(self):
        raw = specs(10)
        raw[8]["options"] = {"registry_source_id": "company-retired"}
        raw += [{"source_id": "lever", "source_type": "ats", "adapter": "lever",
                 "account": "provider-retired"},
                {"source_id": "google-jobs", "source_type": "discovery",
                 "adapter": "serpapi_google", "account": "worldwide"}]
        tables = registry(source_row("company-retired", status="retired"),
                          source_row("lever", status="retired"),
                          source_row("google-jobs", "discovery"))
        batches = plan_free_source_batches(raw, tables, CONFIG, max_sources=20)
        identities = [spec.instance_id for batch in batches for spec in batch]
        self.assertEqual(len(identities), 9)
        self.assertIn("ashby:employer-9", identities)
        self.assertNotIn("ashby:employer-8", identities)
        self.assertFalse(any(key.startswith(("lever:", "google-jobs:"))
                             for key in identities))

    def test_each_round_respects_live_feed_and_source_order(self):
        raw = specs(8) + [
            {"source_id": provider, "source_type": "job_board", "adapter": adapter,
             "account": "feed-" + str(i)}
            for provider, adapter in [("remote-ok", "remoteok"),
                                      ("we-work-remotely", "weworkremotely")]
            for i in range(3)
        ]
        tables = registry(source_row("remote-ok", "job_board"),
                          source_row("we-work-remotely", "job_board"))
        config = {**CONFIG, "direct_discovery_order": "job_board,ats"}
        batches = plan_free_source_batches(raw, tables, config, max_sources=14,
                                           batch_size=4)
        self.assertEqual([spec.source_id for spec in batches[0]],
                         ["we-work-remotely", "we-work-remotely", "ashby", "ashby"])
        self.assertEqual([spec.source_id for spec in batches[1]],
                         ["we-work-remotely", "remote-ok", "ashby", "ashby"])
        self.assertEqual(len({spec.instance_id for batch in batches for spec in batch}), 14)

    def test_source_failures_do_not_retry_or_stop_later_rounds(self):
        source = SourceSpec("ashby", "ats", "ashby", "failed")
        good = SourceSpec("ashby", "ats", "ashby", "good")
        runner = FakeRunner(failed={source.instance_id})
        initial = [{"canonical_url": "https://example.com/jobs/from-google"}]
        result = run_free_discovery_batches(
            runner, [[source, source], [source, good]],
            initial_observations=initial, evaluate=pending, target_verified=5,
        )
        self.assertEqual(runner.calls, [source.instance_id, good.instance_id])
        self.assertEqual(result["fallback_sources_successful"], 1)
        self.assertEqual(result["observations"][0], initial[0])
        self.assertEqual(len(result["observations"]), 2)
        self.assertEqual(len(initial), 1)

    def test_empty_free_plan_still_evaluates_existing_google_observations(self):
        runner = FakeRunner()
        initial = [{"canonical_url": "https://example.com/jobs/google"}]
        result = run_free_discovery_batches(
            runner, [], initial_observations=initial, evaluate=pending,
            target_verified=5,
        )
        self.assertEqual(runner.calls, [])
        self.assertEqual(result["evaluation"]["review_candidates"], initial)
        self.assertEqual(result["source_attempts"], [])

    def test_source_attempts_preserve_success_failure_and_quarantine_without_private_data(self):
        selected = [SourceSpec.from_dict(item) for item in specs(3)]
        results = [
            SourceRunResult(
                source_instance=selected[0].instance_id, registry_source_ids=["ashby", "company-0"],
                started_at="2026-10-19T08:01:00+00:00", success=True,
                fetched=3, normalized=3, complete_snapshot=True,
                observations=[{"canonical_url": "https://private.example/role", "claim": "private claim"}],
            ),
            SourceRunResult(
                source_instance=selected[1].instance_id, registry_source_ids=["ashby", "company-1"],
                started_at="2026-10-19T08:02:00+00:00", success=False,
                fetched=0, normalized=0, failure_category="network_error",
                failure_message="private error https://private.example/?api_key=secret",
            ),
            SourceRunResult(
                source_instance=selected[2].instance_id, registry_source_ids=["ashby", "company-2"],
                started_at="2026-10-19T08:03:00+00:00", success=True,
                fetched=4, normalized=3, quarantine_count=1, complete_snapshot=False,
            ),
        ]
        runner = Mock()
        runner.run_source.side_effect = results
        report = run_free_discovery_batches(
            runner, [selected, [selected[0]]], initial_observations=[],
            evaluate=pending, target_verified=5,
        )
        attempts = report["source_attempts"]
        self.assertEqual(runner.run_source.call_count, 3)
        self.assertEqual(attempts, [
            {"source_instance": "ashby:employer-0", "registry_source_ids": ["ashby", "company-0"],
             "started_at": "2026-10-19T08:01:00+00:00", "success": True, "fetched": 3,
             "normalized": 3, "quarantine_count": 0, "complete_snapshot": True, "failure_category": None},
            {"source_instance": "ashby:employer-1", "registry_source_ids": ["ashby", "company-1"],
             "started_at": "2026-10-19T08:02:00+00:00", "success": False, "fetched": 0,
             "normalized": 0, "quarantine_count": 0, "complete_snapshot": False,
             "failure_category": "network_error"},
            {"source_instance": "ashby:employer-2", "registry_source_ids": ["ashby", "company-2"],
             "started_at": "2026-10-19T08:03:00+00:00", "success": True, "fetched": 4,
             "normalized": 3, "quarantine_count": 1, "complete_snapshot": False, "failure_category": None},
        ])
        encoded = json.dumps(attempts)
        for private in ("private", "secret", "https://", "failure_message", "observations", "claim"):
            self.assertNotIn(private, encoded)

    def test_run_once_audits_google_only_when_a_search_was_attempted(self):
        from test_one_pass_vacancies import ROOT, tables

        for gate, google_failed, free_failed in (
            ("ready", False, False), ("ready", True, False), ("ready", False, True),
            ("not_verified_free_or_insufficient_quota", False, False),
        ):
            with self.subTest(gate=gate, google_failed=google_failed, free_failed=free_failed):
                live_tables = tables()
                before = json.dumps(live_tables, sort_keys=True)
                runner = Mock()

                def run_source(source):
                    failed = google_failed if source.adapter == "serpapi_google" else free_failed
                    return SourceRunResult(
                        source_instance=source.instance_id, registry_source_ids=[source.source_id],
                        started_at="2026-10-19T08:00:00+00:00", success=not failed,
                        fetched=0, normalized=0,
                        failure_category="network_error" if failed else None,
                        failure_message="private error https://private.example/secret" if failed else None,
                    )

                runner.run_source.side_effect = run_source
                with patch("scripts.one_pass_vacancies.google_free_gate", return_value=gate), \
                     patch("scripts.one_pass_vacancies.IngestionRunner", return_value=runner), \
                     patch("scripts.one_pass_vacancies.evaluate_observations", return_value=pending([])), \
                     patch("scripts.one_pass_vacancies._request_json") as external:
                    report = run_once(live_tables, ROOT, "page-1", max_free_sources=1)
                external.assert_not_called()
                self.assertEqual(json.dumps(live_tables, sort_keys=True), before)
                attempts = report["source_attempts"]
                self.assertEqual(len(attempts), 2 if gate == "ready" else 1)
                self.assertEqual([attempt["source_instance"] for attempt in attempts],
                                 [call.args[0].instance_id for call in runner.run_source.call_args_list])
                if gate == "ready":
                    self.assertEqual(attempts[0]["registry_source_ids"], ["google-jobs"])
                    self.assertEqual(attempts[0]["success"], not google_failed)
                self.assertNotIn("private", json.dumps(attempts))
                runner.close.assert_called_once()

        with patch("scripts.one_pass_vacancies.google_free_gate", return_value="ready"), \
             patch("scripts.one_pass_vacancies.IngestionRunner") as runner:
            report = run_once(tables(), ROOT, "check")
        runner.assert_not_called()
        self.assertEqual(report["source_attempts"], [])

    def test_total_failure_cli_keeps_safe_audit_file_and_blocked_exit(self):
        from test_one_pass_vacancies import ROOT, tables

        runner = Mock()
        runner.run_source.side_effect = lambda source: SourceRunResult(
            source_instance=source.instance_id, registry_source_ids=[source.source_id],
            started_at="2026-10-19T08:00:00+00:00", success=False,
            fetched=0, normalized=0, failure_category="network_error",
            failure_message="private error https://private.example/?api_key=secret",
        )
        live_tables = tables()
        before = json.dumps(live_tables, sort_keys=True)
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "blocked.json"
            with patch("sys.argv", ["one_pass_vacancies.py", "--root", str(ROOT),
                                    "--mode", "page-1", "--out", str(out), "--max-free-sources", "2"]), \
                 patch("sys.stdout", new_callable=StringIO) as stdout, \
                 patch("scripts.one_pass_vacancies.load_register", return_value=live_tables), \
                 patch("scripts.one_pass_vacancies.google_free_gate", return_value="not_configured"), \
                 patch("scripts.one_pass_vacancies.IngestionRunner", return_value=runner), \
                 patch("scripts.one_pass_vacancies.evaluate_observations", return_value=pending([])), \
                 patch("scripts.one_pass_vacancies._request_json") as external:
                code = main()
            external.assert_not_called()
            report = json.loads(out.read_text())
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(len(report["source_attempts"]), 2)
        self.assertTrue(all(not attempt["success"] for attempt in report["source_attempts"]))
        self.assertNotIn("final_recommendations", report)
        self.assertEqual(json.dumps(live_tables, sort_keys=True), before)
        for private in ("private", "secret", "https://", "failure_message", "observations", "claim"):
            self.assertNotIn(private, json.dumps(report["source_attempts"]) + stdout.getvalue())
        runner.close.assert_called_once()

    def test_invalid_or_google_plan_fails_before_network(self):
        runner = FakeRunner()
        google = SourceSpec("google-jobs", "discovery", "serpapi_google", "global")
        too_many = [[SourceSpec.from_dict(item)] for item in specs(21)]
        oversized_batch = [[SourceSpec.from_dict(item) for item in specs(9)]]
        for batches in ([[google]], too_many, oversized_batch):
            with self.subTest(plan_size=len(batches)), self.assertRaises(ValueError):
                run_free_discovery_batches(
                    runner, batches, initial_observations=[], evaluate=pending,
                    target_verified=5,
                )
        self.assertEqual(runner.calls, [])

    def test_invalid_budgets_are_rejected(self):
        for limit in (-1, 0, 21, True, 2.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                plan_free_source_batches(specs(3), registry(), CONFIG,
                                          max_sources=limit)
        for batch_size in (0, 9, True):
            with self.subTest(batch_size=batch_size), self.assertRaises(ValueError):
                plan_free_source_batches(specs(3), registry(), CONFIG,
                                          max_sources=3, batch_size=batch_size)

    def test_bounded_snapshot_and_duplicate_round_cannot_close_unseen_role(self):
        spec = SourceSpec("ashby", "ats", "ashby", "acme", max_jobs=2,
                          missing_close_threshold=1)
        known = {"id": "known", "title": "WordPress Developer",
                 "jobUrl": "https://jobs.ashbyhq.com/acme/known"}
        partial = [{"id": str(i), "title": "WordPress Developer",
                    "jobUrl": "https://jobs.ashbyhq.com/acme/new-" + str(i)}
                   for i in range(2)]
        with tempfile.TemporaryDirectory() as temp:
            runner = IngestionRunner(Path(temp) / "state.sqlite3")
            try:
                runner.ingest_records(replace(spec, max_jobs=80), [known])
                with patch("vacature_ingestion.adapters.ashby.AshbyAdapter.fetch",
                           return_value=partial) as fetch:
                    run_free_discovery_batches(
                        runner, [[spec], [spec]], initial_observations=[],
                        evaluate=pending, target_verified=5,
                    )
                fetch.assert_called_once()
                known_row = next(row for row in runner.state.list_jobs()
                                 if row["canonical_url"].endswith("/known"))
                self.assertEqual(known_row["status"], "active")
            finally:
                runner.close()


if __name__ == "__main__":
    unittest.main()
