from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _load(name: str) -> list[dict[str, object]]:
    value = json.loads((ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise AssertionError(f"{name} must contain a JSON array")
    return value


# This is a static contract for the config fetched by live Code.gs on every run.
# No network requests, Google credentials or Apps Script executions are needed.
_DEPLOY_SOURCE_IDS = {
    "wordpressjobs": {"wordpress-jobs"},
    "greenhouse": {"greenhouse"},
    "lever": {"lever"},
    "ashby": {"ashby"},
    "smartrecruiters": {"smartrecruiters"},
    "personio": {"personio"},
    "workable": {"workable"},
    "weworkremotely": {"we-work-remotely"},
    "remoteok": {"remote-ok"},
    "himalayas": {"himalayas"},
    "jobicy": {"jobicy-api"},
    "remotive": {"remotive"},
    "publicfeeds": {
        "remote-landers-api", "remotejobs-org", "arbeitnow-api",
        "working-nomads",
    },
    "teamtailor": {"teamtailor"},
}
_DEPLOY_ENDPOINTS = {
    ("wordpressjobs", "development"):
        "https://jobs.wordpress.net/job_category/development/feed/",
    ("wordpressjobs", "design"):
        "https://jobs.wordpress.net/job_category/design/feed/",
    ("weworkremotely", "programming"):
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    ("remoteok", "global"): "https://remoteok.com/api",
    ("teamtailor", "servebolt"): "https://careers.servebolt.com/jobs.rss",
}
_DEPLOY_FIELDS = {
    "source_id", "source_type", "adapter", "account", "endpoint",
    "listing_language", "max_jobs", "options", "max_response_bytes",
    "timeout_seconds", "retries", "employer",
}
_DEPLOY_OPTION_FIELDS = {
    "discovery_only", "registry_source_id", "original_date_detail_limit",
    "page_size", "language", "feed_scope", "attribution_required",
    "canonical_verification_required", "query", "sort",
    "refresh_semantics", "tag", "rss_fallback_url",
    "feed_delay_hours", "provider_date_not_original",
}


def _validate_deploy_spec_contract(specs: object) -> None:
    """Fail closed on unexpected identities, request targets and schema drift.

    The source is fetched from raw.githubusercontent.com/main by the live
    scanner, so editing specs could change live behavior without changing
    Code.gs or triggering its guarded auto-deploy workflow.
    """
    if not isinstance(specs, list) or not specs:
        raise ValueError("Deploy specifications must be a nonempty list")
    seen: set[tuple[str, str]] = set()
    for spec in specs:
        if not isinstance(spec, dict):
            raise ValueError("Deploy source entry must be an object")
        if set(spec) - _DEPLOY_FIELDS or "status" in spec:
            raise ValueError("Unexpected deploy field")
        adapter, source_id = spec.get("adapter"), spec.get("source_id")
        if adapter not in _DEPLOY_SOURCE_IDS:
            raise ValueError("Unapproved deploy adapter")
        if source_id not in _DEPLOY_SOURCE_IDS[adapter]:
            raise ValueError("Unapproved adapter to Register source binding")
        account = spec.get("account")
        if not isinstance(account, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,80}", account
        ):
            raise ValueError("Unsafe ATS account name")
        key = (source_id, account)
        if key in seen:
            raise ValueError("Duplicate source instance")
        seen.add(key)
        if spec.get("source_type") not in {
            "ats", "wordpress_discovery", "job_board", "discovery_api"
        }:
            raise ValueError("Unapproved source type")
        if "listing_language" in spec and spec["listing_language"] not in {
            "en", "nl"
        }:
            raise ValueError("Unapproved listing language")
        jobs = spec.get("max_jobs")
        if type(jobs) is not int or not 1 <= jobs <= 20000:
            raise ValueError("Unbounded or malformed max_jobs")
        expected_endpoint = _DEPLOY_ENDPOINTS.get((adapter, account))
        if expected_endpoint is None:
            if "endpoint" in spec:
                raise ValueError("Unexpected network endpoint")
        elif spec.get("endpoint") != expected_endpoint:
            raise ValueError("Changed approved HTTPS endpoint")
        if adapter == "teamtailor" and (
            account != "servebolt" or spec.get("employer") != "Servebolt"
            or (spec.get("options") or {}).get("registry_source_id")
            != "company-servebolt"
        ):
            raise ValueError("Changed pinned Servebolt feed identity")
        if adapter == "publicfeeds" and "endpoint" in spec:
            raise ValueError("Publicfeeds are not a live Apps Script adapter")
        for field, upper in (
            ("max_response_bytes", 4250000), ("timeout_seconds", 60),
            ("retries", 2),
        ):
            if field in spec and (
                type(spec[field]) is not int
                or not 0 <= spec[field] <= upper
            ):
                raise ValueError("Invalid request budget")
        options = spec.get("options", {})
        if not isinstance(options, dict) or set(options) - _DEPLOY_OPTION_FIELDS:
            raise ValueError("Unexpected nested source options")
        registry_id = options.get("registry_source_id")
        if registry_id is not None and (
            not isinstance(registry_id, str)
            or not re.fullmatch(r"company-[a-z0-9-]+", registry_id)
        ):
            raise ValueError("Unsafe employer Register binding")
        fallback = options.get("rss_fallback_url")
        if fallback is not None and (
            (adapter, fallback) !=
            ("jobicy", "https://jobicy.com/jobs/feed")
        ):
            raise ValueError("Unapproved nested URL")
        region = options.get("api_region")
        if region is not None and (
            adapter != "lever" or region != "eu"
        ):
            raise ValueError("Unapproved provider API region")


class SourceSpecTests(unittest.TestCase):
    def test_only_two_technical_source_configurations_remain(self):
        files = sorted(p.name for p in ROOT.glob("source-specs.*.json"))
        self.assertEqual(["source-specs.deploy.json", "source-specs.google-optional.json"], files)

    def test_deploy_source_instances_are_unique(self):
        specs = _load("source-specs.deploy.json")
        keys = [(spec.get("source_id"), spec.get("account")) for spec in specs]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertGreaterEqual(len(specs), 20)
        self.assertTrue(all("status" not in spec for spec in specs))

    def test_core_free_feeds_remain_in_deploy(self):
        specs = _load("source-specs.deploy.json")
        ids = {str(spec.get("source_id")) for spec in specs}
        self.assertTrue({"we-work-remotely", "remote-ok", "himalayas", "jobicy-api", "remotive"}.issubset(ids))

    def test_wordpress_and_automation_employer_adapters_remain(self):
        specs = _load("source-specs.deploy.json")
        n8n = [spec for spec in specs if spec.get("source_id") == "ashby" and spec.get("account") == "n8n"]
        human_made = [spec for spec in specs if spec.get("employer") == "Human Made"]
        self.assertEqual(1, len(n8n))
        self.assertEqual("company-n8n", n8n[0].get("options", {}).get("registry_source_id"))
        self.assertEqual(1, len(human_made))
        self.assertEqual("workable", human_made[0].get("adapter"))

    def test_working_nomads_is_bounded_discovery_only(self):
        specs = _load("source-specs.deploy.json")
        board = [spec for spec in specs if spec.get("source_id") == "working-nomads"]
        self.assertEqual(1, len(board))
        self.assertEqual("publicfeeds", board[0].get("adapter"))
        self.assertLessEqual(board[0].get("max_jobs"), 60)
        self.assertIsNone(board[0].get("endpoint"))
        self.assertTrue(board[0].get("options", {}).get("discovery_only"))

    def test_official_wordpress_jobs_rss_only_through_register_owned_source(self):
        specs = _load("source-specs.deploy.json")
        feeds = [s for s in specs if s.get("adapter") == "wordpressjobs"]
        self.assertEqual(len(feeds), 2)
        self.assertEqual({s["account"] for s in feeds}, {"development", "design"})
        self.assertTrue(all(s["source_id"] == "wordpress-jobs" for s in feeds))
        self.assertTrue(all(s["source_type"] == "wordpress_discovery" for s in feeds))
        self.assertTrue(all(s["endpoint"] ==
            "https://jobs.wordpress.net/job_category/" + s["account"] + "/feed/"
            for s in feeds))
        self.assertTrue(all(s["max_response_bytes"] <= 1048576 for s in feeds))

    def test_google_requires_explicit_registered_source(self):
        google = _load("source-specs.google-optional.json")
        self.assertEqual(1, len(google))
        self.assertEqual("google-jobs", google[0].get("source_id"))

    def test_google_queries_target_wordpress_roles_only(self):
        google = _load("source-specs.google-optional.json")
        options = google[0].get("options", {})
        queries = options.get("queries", [])
        self.assertEqual(4, len(queries))
        combined = "\n".join(queries).casefold()
        self.assertIn("woocommerce", combined)
        self.assertIn("elementor", combined)
        self.assertIn("wordpress support", combined)
        self.assertNotIn("ai workflow automation", combined)


    def test_deploy_config_has_safe_hosts_schema_and_register_bindings(self):
        _validate_deploy_spec_contract(_load("source-specs.deploy.json"))

    def test_deploy_config_rejects_unsafe_mutations(self):
        # Demonstrate FAIL on malicious/accidental changes, without writes.
        from copy import deepcopy
        base = _load("source-specs.deploy.json")
        cases = {
            "duplicate": lambda rows: rows.append(deepcopy(rows[0])),
            "adapter": lambda rows: rows[0].update(adapter="custom-http"),
            "register_binding": lambda rows: rows[0].update(source_id="company-unknown"),
            "unapproved_host": lambda rows: rows[0].update(
                endpoint="https://unapproved.example/jobs"
            ),
            "plain_http": lambda rows: rows[0].update(
                endpoint="http://jobs.wordpress.net/job_category/development/feed/"
            ),
            "account_traversal": lambda rows: rows[0].update(account="../private"),
            "unexpected_status": lambda rows: rows[0].update(status="active"),
            "nested_url": lambda rows: rows[0].update(
                options={"rss_fallback_url": "https://unapproved.example/feed"}
            ),
            "unbounded_jobs": lambda rows: rows[0].update(max_jobs=100000),
        }
        for description, change in cases.items():
            with self.subTest(mutation=description):
                modified = deepcopy(base)
                change(modified)
                with self.assertRaises(ValueError):
                    _validate_deploy_spec_contract(modified)

if __name__ == "__main__":
    unittest.main()
