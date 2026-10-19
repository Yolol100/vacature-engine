"""Bounded free discovery: no live requests, score fabrication or Register writes."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.one_pass_vacancies import (
    plan_free_source_batches, run_free_discovery_batches, select_free_specs,
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
