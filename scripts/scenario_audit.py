#!/usr/bin/env python3
"""Deterministic high-volume scenario audit for critical vacancy-engine invariants."""
from __future__ import annotations

import json
import math
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vacature_engine.core import canonical_url, content_hash  # noqa: E402
from vacature_engine.http import validate_public_url  # noqa: E402
from vacature_engine.models import JobRecord  # noqa: E402
from vacature_engine.pipeline import filter_recency  # noqa: E402
from vacature_engine.policy import application_guard, hard_gate, score  # noqa: E402
from vacature_engine.structured import jobposting_facts  # noqa: E402


class Audit:
    def __init__(self) -> None:
        self.total = 0
        self.failures: list[str] = []

    def check(self, name: str, condition: bool) -> None:
        self.total += 1
        if not condition:
            self.failures.append(name)


def good_gate() -> dict[str, object]:
    return {
        "posted_age_days": 2,
        "active": True,
        "official_link_working": True,
        "fully_remote": True,
        "netherlands_eligibility": "allowed",
        "level": "Senior Engineer",
        "central_hard_mismatch_count": 0,
    }


def perfect_score() -> dict[str, object]:
    return {
        "hard_requirements": 35,
        "experience_seniority": 20,
        "cv_portfolio_evidence": 15,
        "wordpress_stack": 10,
        "quality_stack": 10,
        "communication_autonomy": 5,
        "preferred_requirements": 5,
        "freshness": 15,
        "competition": 10,
        "netherlands_certainty": 10,
        "employer_credibility": 5,
        "compensation_contract_fit": 5,
        "central_hard_missing": False,
        "multiple_central_hard_mismatches": False,
    }


def good_draft() -> dict[str, object]:
    return {
        "stage": "draft",
        "user_explicitly_requested": True,
        "final_verification_pass": True,
        "hard_gate_pass": True,
        "cv_selected": True,
        "recipient_verified": True,
        "recipient_authorized_for_role": True,
        "recipient_email": "jobs@example.com",
        "recipient_source_url": "https://example.com/jobs/1",
        "factual_qa": "pass",
        "style_qa": "pass",
        "cv_attachment_ready": True,
        "subject_exact_vacancy_title": True,
    }


def run_audit() -> dict[str, object]:
    audit = Audit()

    audit.check("gate_baseline", hard_gate(good_gate())["pass"] is True)
    for flag in (
        "mandatory_relocation",
        "structural_office_attendance",
        "unpaid_test",
        "commission_only",
        "suspicious_payment",
        "marketplace_excluded",
        "duplicate",
        "us_residents_only",
    ):
        data = good_gate()
        data[flag] = True
        audit.check(f"gate_flag_{flag}", hard_gate(data)["pass"] is False)

    for age in [0, 0.01, 1, 3.5, 6.99, 7]:
        data = good_gate()
        data["posted_age_days"] = age
        audit.check(f"gate_age_pass_{age}", hard_gate(data)["pass"] is True)
    for index, age in enumerate([None, True, False, -1, -0.001, 7.0001, 8, math.nan, math.inf, -math.inf, "2"]):
        data = good_gate()
        data["posted_age_days"] = age
        audit.check(f"gate_age_fail_{index}", hard_gate(data)["pass"] is False)

    for level in (
        "Medior Developer",
        "Mid-level Developer",
        "Mid level Engineer",
        "Senior WordPress Developer",
        "Lead Engineer",
        "Principal Engineer",
        "Staff Engineer",
        "Accessibility Specialist",
        "Technical Consultant",
        "Autonomous WordPress Developer",
        "SEO Expert",
    ):
        data = good_gate()
        data["level"] = level
        audit.check(f"level_pass_{level}", hard_gate(data)["pass"] is True)
    for level in (
        "Software Engineer",
        "Developer",
        "Junior Engineer",
        "Engineering Intern",
        "Graduate Engineer",
        "Entry-level Developer",
        "Trainee Developer",
        "Apprentice Developer",
        "",
    ):
        data = good_gate()
        data["level"] = level
        audit.check(f"level_fail_{level}", hard_gate(data)["pass"] is False)

    for nl in ("allowed", "plausible"):
        data = good_gate()
        data["netherlands_eligibility"] = nl
        audit.check(f"nl_pass_{nl}", hard_gate(data)["pass"] is True)
    for nl in (None, "denied", "unknown", "us-only", True):
        data = good_gate()
        data["netherlands_eligibility"] = nl
        audit.check(f"nl_fail_{nl}", hard_gate(data)["pass"] is False)

    component_max = {
        "hard_requirements": 35,
        "experience_seniority": 20,
        "cv_portfolio_evidence": 15,
        "wordpress_stack": 10,
        "quality_stack": 10,
        "communication_autonomy": 5,
        "preferred_requirements": 5,
        "freshness": 15,
        "competition": 10,
        "netherlands_certainty": 10,
        "employer_credibility": 5,
        "compensation_contract_fit": 5,
    }
    for key, maximum in component_max.items():
        for value in (0, maximum / 2, maximum):
            data = perfect_score()
            data[key] = value
            try:
                result = score(data)
                ok = math.isfinite(result["match_score"]) and math.isfinite(result["opportunity_score"])
            except ValueError:
                ok = False
            audit.check(f"score_valid_{key}_{value}", ok)
        for index, value in enumerate((-0.01, maximum + 0.01, True, math.nan, math.inf, -math.inf, "1")):
            data = perfect_score()
            data[key] = value
            try:
                score(data)
                ok = False
            except ValueError:
                ok = True
            audit.check(f"score_invalid_{key}_{index}", ok)

    capped = perfect_score()
    capped["central_hard_missing"] = True
    audit.check("score_cap_59", score(capped)["match_score"] == 59.0)
    excluded = perfect_score()
    excluded["multiple_central_hard_mismatches"] = True
    audit.check("score_multiple_excluded", score(excluded)["excluded"] is True)

    audit.check("draft_baseline", application_guard(good_draft())["pass"] is True)
    for key, bad in {
        "user_explicitly_requested": False,
        "final_verification_pass": False,
        "hard_gate_pass": False,
        "cv_selected": False,
        "recipient_verified": False,
        "recipient_authorized_for_role": False,
        "factual_qa": "fail",
        "style_qa": "fail",
        "cv_attachment_ready": False,
        "subject_exact_vacancy_title": False,
    }.items():
        data = good_draft()
        data[key] = bad
        audit.check(f"draft_block_{key}", application_guard(data)["pass"] is False)
    for index, email in enumerate(("a@", "@example.com", "a b@example.com", "example.com", "")):
        data = good_draft()
        data["recipient_email"] = email
        audit.check(f"draft_bad_email_{index}", application_guard(data)["pass"] is False)

    rng = random.Random(20260825)
    base = "https://Example.com/jobs/42?a=1&b=2"
    canonical = canonical_url(base)
    tracking = ["utm_source", "utm_campaign", "gclid", "fbclid", "ref", "source"]
    for index in range(100):
        params = [f"{key}={rng.randint(1, 99999)}" for key in rng.sample(tracking, k=rng.randint(1, len(tracking)))]
        variant = base + "&" + "&".join(params) + ("#section" if index % 2 else "")
        audit.check(f"canonical_tracking_{index}", canonical_url(variant) == canonical)

    reference = content_hash("Senior WordPress Developer with WooCommerce")
    for index in range(30):
        noise = " " * (index % 5 + 1)
        variant = f"{noise}SENIOR{noise}WordPress Developer with WooCommerce https://track.example/{index}{noise}"
        audit.check(f"hash_noise_{index}", content_hash(variant) == reference)
    for index in range(20):
        audit.check(
            f"hash_material_{index}",
            content_hash(f"Senior WordPress Developer requirement {index}") != reference,
        )

    now = datetime.now(UTC)
    for days in (0, 1, 3, 6.999):
        item = JobRecord("x", str(days), "Senior Dev", "Acme", f"https://example.com/{days}", posted_at=(now - timedelta(days=days)).isoformat())
        fresh, _ = filter_recency([item], 7)
        audit.check(f"recency_past_{days}", len(fresh) == 1)
    for days in (0.001, 1, 30):
        item = JobRecord("x", f"f{days}", "Senior Dev", "Acme", f"https://example.com/f{days}", posted_at=(now + timedelta(days=days)).isoformat())
        fresh, unknown = filter_recency([item], 7)
        audit.check(f"recency_future_{days}", not fresh and not unknown)

    for index, invalid_window in enumerate((True, float("nan"), float("inf"), -float("inf"))):
        try:
            filter_recency([], invalid_window)
            ok = False
        except ValueError:
            ok = True
        audit.check(f"recency_invalid_window_{index}", ok)

    blocked_urls = (
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://169.254.169.254/",
        "http://localhost/",
        "http://service.internal/",
        "http://intranet/",
        "https://example.com:8443/",
        "https://user:pass@example.com/",
    )
    for index, url in enumerate(blocked_urls):
        try:
            validate_public_url(url)
            ok = False
        except (ValueError, RuntimeError):
            ok = True
        audit.check(f"target_block_{index}", ok)

    for index in range(20):
        country = "NL" if index % 2 == 0 else "DE"
        payload = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": f"Senior Developer {index}",
            "datePosted": "2026-08-24",
            "jobLocationType": "TELECOMMUTE",
            "applicantLocationRequirements": {"@type": "Country", "name": country},
        }
        html = f'<script type="application/ld+json">{json.dumps(payload)}</script>'
        facts = jobposting_facts(html)[0]
        audit.check(f"jsonld_remote_{index}", facts["fully_remote_signal"] is True)
        audit.check(f"jsonld_country_{index}", facts["netherlands_explicit"] is (country == "NL"))

    return {
        "pass": not audit.failures,
        "scenario_count": audit.total,
        "failure_count": len(audit.failures),
        "failures": audit.failures,
    }


def main() -> int:
    result = run_audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
