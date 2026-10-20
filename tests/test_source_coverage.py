"""Offline, deterministic coverage/Google planning regressions (no provider calls)."""
import unittest

from scripts.source_coverage import build_source_coverage, complete_source_coverage


def fixture(public_count=14):
    rows = [
        {"source_id": "ashby", "status": "active", "source_type": "ats",
         "priority": "high", "base_url": "https://jobs.ashbyhq.com/"},
        {"source_id": "google-jobs", "status": "active", "source_type": "discovery",
         "base_url": "https://www.google.com/search"},
        {"source_id": "old-board", "status": "retired", "source_type": "job_board",
         "base_url": "https://old.example.org"},
        {"source_id": "merged-board", "status": "consolidated", "source_type": "job_board",
         "base_url": "https://merged.example.org"},
        {"source_id": "mail-evidence", "status": "active",
         "source_type": "application_evidence",
         "base_url": "https://mail.example.org"},
        {"source_id": "unsafe-internal", "status": "active",
         "source_type": "job_board", "base_url": "https://internal.local/jobs"},
    ]
    rows.extend({
        "source_id": f"employer-{i}", "status": "active",
        "source_type": "employer_direct",
        "priority": "high" if i < 2 else "medium",
        "base_url": f"https://careers{i}.example.org/jobs",
    } for i in range(public_count))
    config = {
        "target_role_search_terms": "wordpress,woocommerce,elementor,gutenberg",
        "vacancy_specialized_search_terms": "woocommerce,n8n,AI workflow",
        "google_xray_domains": "jobs.ashbyhq.com,jobs.lever.co,apply.workable.com",
        "high_source_order": "employer-1,employer-0",
    }
    deploy = [{"source_id": "ashby", "adapter": "ashby"}]
    seeds = [
        "site:jobs.ashbyhq.com WordPress remote",
        "AI workflow automation engineer remote Europe",
    ]
    return rows, config, deploy, seeds


def planned(*, public_count=14, round_index=0, budget=8, pages=1):
    rows, config, deploy, seeds = fixture(public_count)
    return build_source_coverage(
        rows, deploy, config, seeds,
        round_index=round_index, max_google_queries=budget, pages=pages,
    )


class SourceCoverageTests(unittest.TestCase):
    def test_every_registered_source_is_classified_without_false_scans(self):
        report = planned(public_count=14)
        self.assertEqual(report["summary"]["registered_total"], 20)
        self.assertEqual(report["summary"]["active_total"], 18)
        self.assertEqual(report["summary"]["inactive_total"], 2)
        self.assertEqual(report["summary"]["adapter_registered"], 1)
        self.assertEqual(report["summary"]["non_vacancy"], 1)
        self.assertEqual(report["summary"]["unavailable_public_site"], 1)
        self.assertEqual(report["summary"]["google_site_eligible"], 14)
        states = {row["source_id"]: row for row in report["sources"]}
        self.assertEqual(states["old-board"]["execution"], "excluded")
        self.assertEqual(states["merged-board"]["execution"], "excluded")
        self.assertEqual(states["mail-evidence"]["execution"], "not_applicable")
        self.assertEqual(states["ashby"]["execution"], "not_attempted")
        self.assertTrue(all(x["execution"] != "direct_attempt_succeeded"
                            for x in report["sources"]))

    def test_rounds_rotate_all_public_sources_without_losing_existing_adapters(self):
        seen = set()
        for rnd in range(5):
            plan = planned(public_count=14, round_index=rnd)
            seen.update(q["source_id"] for q in plan["query_plan"]
                        if q["lane"] == "registered_source_domain")
            self.assertLessEqual(plan["google_request_budget"], 50)
            self.assertEqual(plan["summary"]["adapter_registered"], 1)
            self.assertTrue(all(q["lane"] != "registered_source_domain"
                                or q["source_id"].startswith("employer-")
                                for q in plan["query_plan"]))
        self.assertEqual(seen, {f"employer-{i}" for i in range(14)})
        self.assertNotEqual(planned(round_index=0)["query_plan"],
                            planned(round_index=1)["query_plan"])

    def test_rotating_xray_pairs_reach_full_configured_domain_term_universe(self):
        pairs = set()
        for rnd in range(16):
            plan = planned(round_index=rnd)
            self.assertEqual(plan["specialized_search_terms"], 6)
            self.assertEqual(plan["configured_xray_domains"], 3)
            self.assertEqual(plan["possible_xray_pairs"], 18)
            pairs.update(q["query"] for q in plan["query_plan"]
                         if q["lane"] == "configured_xray_domain")
        self.assertEqual(len(pairs), 18)

    def test_free_quota_budget_is_hard_capped_even_for_deep_modes(self):
        for pages, expected_max in ((0, 20), (1, 20), (3, 16), (10, 5)):
            with self.subTest(pages=pages):
                rows, cfg, deployed, seeds = fixture()
                report = build_source_coverage(
                    rows, deployed, cfg, seeds,
                    round_index=0, max_google_queries=20, pages=pages)
                self.assertLessEqual(report["google_query_count"], expected_max)
                self.assertLessEqual(report["google_request_budget"], 50)
        for invalid in (-1, "one", True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    build_source_coverage(*fixture()[:1], [], {}, [],
                        round_index=invalid, max_google_queries=8, pages=1)

    def test_private_or_invalid_registry_urls_never_become_google_queries(self):
        rows, cfg, specs, seeds = fixture(public_count=0)
        rows.extend([
            {"source_id": "bad-auth", "status": "active", "source_type": "job_board",
             "base_url": "https://username:pass@example.org/jobs"},
            {"source_id": "bad-ip", "status": "active", "source_type": "job_board",
             "base_url": "http://127.0.0.1/jobs"},
            {"source_id": "bad-port", "status": "active", "source_type": "job_board",
             "base_url": "https://example.org:9443/jobs"},
            {"source_id": "bad-script", "status": "active", "source_type": "job_board",
             "base_url": "javascript:alert(1)"},
        ])
        cfg["google_xray_domains"] = "127.0.0.1,internal.local,jobs.ashbyhq.com"
        cfg["target_role_search_terms"] += ',"private:key"'
        report = build_source_coverage(
            rows, specs, cfg, seeds, round_index=0,
            max_google_queries=8, pages=1)
        self.assertEqual(report["summary"]["unavailable_public_site"], 5)
        self.assertEqual(report["configured_xray_domains"], 1)
        forbidden = ("bad-auth", "bad-ip", "bad-port", "bad-script", "private:key")
        self.assertFalse(any(any(term in q["query"] for term in forbidden)
                             for q in report["query_plan"]))

    def test_completed_status_distinguishes_direct_from_google_hints(self):
        plan = planned()
        completed = complete_source_coverage(
            plan, google_status="searched", mode="page-1", source_attempts=[
                {"source_instance": "ashby:tenant", "registry_source_ids": ["ashby"],
                 "success": True, "fetched": 3},
            ])
        entries = {row["source_id"]: row for row in completed["sources"]}
        self.assertEqual(entries["ashby"]["execution"], "direct_attempt_succeeded")
        self.assertEqual(entries["google-jobs"]["execution"],
                         "google_provider_batch_succeeded")
        self.assertTrue(any(
            x["execution"] == "google_batch_succeeded_query_unconfirmed"
            for x in completed["sources"]))
        self.assertFalse(any(x["coverage_route"] == "google_site_discovery_only"
                             and x["execution"] == "direct_attempt_succeeded"
                             for x in completed["sources"]))
        check = complete_source_coverage(
            plan, google_status="ready", mode="check", source_attempts=[])
        self.assertEqual(check["sources"][0]["execution"], "not_attempted")
        self.assertTrue(all("succeeded" not in x["execution"]
                            for x in check["sources"]))

    def test_employer_tenant_is_direct_only_when_both_register_ids_active(self):
        rows, cfg, _, seeds = fixture(public_count=0)
        rows.extend([
            {"source_id": "greenhouse", "status": "active",
             "source_type": "ats", "base_url": "https://boards.greenhouse.io"},
            {"source_id": "company-example", "status": "active",
             "source_type": "employer_direct",
             "base_url": "https://example.org/careers"},
        ])
        spec = [{"source_id": "greenhouse", "adapter": "greenhouse",
                 "options": {"registry_source_id": "company-example"}}]
        good = build_source_coverage(
            rows, spec, cfg, seeds,
            round_index=0, max_google_queries=8, pages=1)
        entries = {r["source_id"]: r for r in good["sources"]}
        self.assertEqual(entries["greenhouse"]["coverage_route"], "public_adapter")
        self.assertEqual(entries["company-example"]["coverage_route"], "public_adapter")
        completed = complete_source_coverage(
            good, google_status="not_configured", mode="page-1",
            source_attempts=[{
                "source_instance": "greenhouse:example",
                "registry_source_ids": ["greenhouse", "company-example"],
                "success": True,
            }])
        statuses = {r["source_id"]: r["execution"] for r in completed["sources"]}
        self.assertEqual(statuses["greenhouse"], "direct_attempt_succeeded")
        self.assertEqual(statuses["company-example"], "direct_attempt_succeeded")
        rows[-1]["status"] = "retired"
        disabled = build_source_coverage(
            rows, spec, cfg, seeds,
            round_index=0, max_google_queries=8, pages=1)
        indexed = {r["source_id"]: r for r in disabled["sources"]}
        self.assertNotEqual(indexed["greenhouse"]["coverage_route"], "public_adapter")
        self.assertEqual(indexed["company-example"]["execution"], "excluded")

    def test_live_discovery_class_order_beats_unrelated_board_priority(self):
        rows, cfg, deploy, seeds = fixture(public_count=0)
        rows.extend([
            {"source_id": "board-priority", "status": "active",
             "source_type": "job_board", "priority": "high",
             "base_url": "https://jobs.example.org"},
            {"source_id": "direct-employer", "status": "active",
             "source_type": "employer_direct", "priority": "medium",
             "base_url": "https://careers.example.org"},
        ])
        cfg["direct_discovery_order"] = "employer_direct,ats,job_board"
        report = build_source_coverage(
            rows, deploy, cfg, seeds, round_index=0,
            max_google_queries=8, pages=1)
        first = next(q for q in report["query_plan"]
                     if q["lane"] == "registered_source_domain")
        self.assertEqual(first["source_id"], "direct-employer")

    def test_default_eight_queries_give_xray_a_real_four_slot_window(self):
        plan = planned(public_count=14)
        from collections import Counter
        lanes = Counter(q["lane"] for q in plan["query_plan"])
        self.assertEqual(plan["google_query_count"], 8)
        self.assertEqual(lanes["registered_source_domain"], 3)
        self.assertEqual(lanes["configured_xray_domain"], 4)
        self.assertEqual(lanes["registered_google_seed"], 1)
        self.assertEqual(plan["google_request_budget"], 8)
        self.assertEqual(len({q["query"] for q in plan["query_plan"]}), 8)

    def test_no_xray_domains_uses_remaining_free_budget_for_sources(self):
        rows, cfg, deploy, seeds = fixture(public_count=14)
        cfg["google_xray_domains"] = ""
        plan = build_source_coverage(rows, deploy, cfg, seeds,
                                     round_index=2, max_google_queries=8, pages=1)
        self.assertEqual(plan["google_query_count"], 8)
        self.assertTrue(all(q["lane"] in {
            "registered_source_domain", "registered_google_seed",
        } for q in plan["query_plan"]))

    def test_duplicate_source_ids_fail_closed(self):
        rows, cfg, deployed, seeds = fixture()
        rows.append(dict(rows[0]))
        with self.assertRaises(ValueError):
            build_source_coverage(
                rows, deployed, cfg, seeds,
                round_index=0, max_google_queries=8, pages=1)


if __name__ == "__main__":
    unittest.main()
