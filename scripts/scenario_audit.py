#!/usr/bin/env python3
"""Deterministic high-volume scenario audit for critical vacancy-engine invariants."""
from __future__ import annotations

import itertools
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
from vacature_engine.policy import (  # noqa: E402
    MATCH_COMPONENTS,
    OPPORTUNITY_COMPONENTS,
    application_guard,
    hard_gate,
    score,
)
from vacature_engine.structured import jobposting_facts  # noqa: E402


class Audit:
    def __init__(self) -> None:
        self.total = 0
        self.failures: list[str] = []

    def check(self, name: str, condition: bool) -> None:
        self.total += 1
        if not condition:
            self.failures.append(name)


def good_gate(**overrides) -> dict[str, object]:
    data: dict[str, object] = {
        "posted_age_days": 2,
        "active": True,
        "official_link_working": True,
        "fully_remote": True,
        "work_eligibility": "allowed",
        "mandatory_relocation": False,
        "structural_office_attendance": False,
        "unpaid_test": False,
        "commission_only": False,
        "suspicious_payment": False,
        "marketplace_excluded": False,
        "duplicate": False,
        "stale_repost": False,
        "geographic_restriction_blocks": False,
        "us_residents_only": False,
        "level": "Senior Engineer",
        "central_hard_mismatch_count": 0,
    }
    data.update(overrides)
    return data


def perfect_score(**overrides) -> dict[str, object]:
    data: dict[str, object] = {
        "hard_requirements": 35,
        "experience_seniority": 20,
        "cv_portfolio_evidence": 15,
        "wordpress_stack": 10,
        "quality_stack": 10,
        "communication_autonomy": 5,
        "preferred_requirements": 5,
        "freshness": 15,
        "competition": 10,
        "work_eligibility_certainty": 10,
        "employer_credibility": 5,
        "compensation_contract_fit": 5,
        "central_hard_missing": False,
        "multiple_central_hard_mismatches": False,
    }
    data.update(overrides)
    return data


def good_draft(**overrides) -> dict[str, object]:
    data: dict[str, object] = {
        "stage": "draft",
        "user_explicitly_requested": True,
        "final_verification_pass": True,
        "hard_gate_pass": True,
        "cv_selected": True,
        "work_eligibility_confirmed": True,
        "legitimacy_check_pass": True,
        "recipient_verified": True,
        "recipient_authorized_for_role": True,
        "recipient_email": "jobs@example.com",
        "recipient_source_url": "https://example.com/jobs/1",
        "factual_qa": "pass",
        "style_qa": "pass",
        "motivation_qa_pass": True,
        "cv_attachment_ready": True,
        "subject_exact_vacancy_title": True,
    }
    data.update(overrides)
    return data


def run_audit() -> dict[str, object]:
    audit = Audit()

    blocking = (
        "mandatory_relocation",
        "structural_office_attendance",
        "unpaid_test",
        "commission_only",
        "suspicious_payment",
        "marketplace_excluded",
        "duplicate",
        "stale_repost",
        "geographic_restriction_blocks",
        "us_residents_only",
    )
    for bits in itertools.product((False, True), repeat=len(blocking)):
        data = good_gate(**dict(zip(blocking, bits, strict=True)))
        audit.check(f"gate_blocking_{bits}", hard_gate(data)["pass"] is (not any(bits)))

    ages = (-0.01, 0, 2, 7, 7.01, None)
    eligibilities = ("allowed", "plausible", "blocked", "unknown")
    remotes = (True, False)
    actives = (True, False)
    links = (True, False)
    levels: tuple[object, ...] = (
        "Senior Engineer",
        "Medior Developer",
        "Junior Developer",
        "Software Engineer",
        ["Senior"],
    )
    for age, eligibility, remote, active, link, level in itertools.product(
        ages, eligibilities, remotes, actives, links, levels
    ):
        result = hard_gate(
            good_gate(
                posted_age_days=age,
                work_eligibility=eligibility,
                fully_remote=remote,
                active=active,
                official_link_working=link,
                level=level,
            )
        )
        age_ok = (
            isinstance(age, (int, float))
            and not isinstance(age, bool)
            and math.isfinite(float(age))
            and 0 <= age <= 7
        )
        level_ok = (
            isinstance(level, str)
            and ("senior" in level.lower() or "medior" in level.lower())
            and "junior" not in level.lower()
        )
        expected = (
            age_ok
            and eligibility in {"allowed", "plausible"}
            and remote
            and active
            and link
            and level_ok
        )
        audit.check("gate_state_cartesian", result["pass"] is expected)

    for value in (None, True, 1, 1.5, [], {}, {"allowed"}):
        result = hard_gate(good_gate(work_eligibility=value))
        audit.check(f"eligibility_type_{value!r}", result["pass"] is False)
    for value in (None, True, 1, ["Senior"], {"level": "Senior"}):
        result = hard_gate(good_gate(level=value))
        audit.check(
            f"level_type_{value!r}",
            result["pass"] is False and "invalid_level" in result["reasons"],
        )
    for count, expected_pass in ((0, True), (1, False), (2, False)):
        result = hard_gate(good_gate(central_hard_mismatch_count=count))
        audit.check(f"central_mismatch_{count}", result["pass"] is expected_pass)
    for value in (True, -1, 1.5, "1"):
        result = hard_gate(good_gate(central_hard_mismatch_count=value))
        audit.check(f"central_mismatch_invalid_{value!r}", result["pass"] is False)

    maxima = {**MATCH_COMPONENTS, **OPPORTUNITY_COMPONENTS}
    score_keys = list(maxima)
    for bits in itertools.product((0, 1), repeat=len(score_keys)):
        data = perfect_score()
        for key, bit in zip(score_keys, bits, strict=True):
            data[key] = maxima[key] if bit else 0
        result = score(data)
        expected_match = sum(float(data[k]) for k in MATCH_COMPONENTS)
        expected_opp = expected_match * 0.55 + sum(
            float(data[k]) for k in OPPORTUNITY_COMPONENTS
        )
        audit.check("score_match_cartesian", result["match_score"] == round(expected_match, 1))
        audit.check("score_opp_cartesian", result["opportunity_score"] == round(expected_opp, 1))

    for key, maximum in maxima.items():
        for value in (True, False, -0.01, maximum + 0.01, math.nan, math.inf, -math.inf, "1"):
            try:
                score(perfect_score(**{key: value}))
                ok = False
            except ValueError:
                ok = True
            audit.check(f"score_invalid_{key}_{value!r}", ok)

    audit.check(
        "score_cap_59",
        score(perfect_score(central_hard_missing=True))["match_score"] == 59.0,
    )
    audit.check(
        "score_multiple_excluded",
        score(perfect_score(multiple_central_hard_mismatches=True))["excluded"] is True,
    )

    prepare_keys = (
        "user_explicitly_requested",
        "final_verification_pass",
        "hard_gate_pass",
        "cv_selected",
        "work_eligibility_confirmed",
        "legitimacy_check_pass",
    )
    for bits in itertools.product((False, True), repeat=len(prepare_keys)):
        data = {"stage": "prepare", **dict(zip(prepare_keys, bits, strict=True))}
        audit.check(f"prepare_{bits}", application_guard(data)["pass"] is all(bits))

    draft_keys = (
        "user_explicitly_requested",
        "final_verification_pass",
        "hard_gate_pass",
        "cv_selected",
        "work_eligibility_confirmed",
        "legitimacy_check_pass",
        "recipient_verified",
        "recipient_authorized_for_role",
        "motivation_qa_pass",
        "cv_attachment_ready",
        "subject_exact_vacancy_title",
    )
    for bits in itertools.product((False, True), repeat=len(draft_keys)):
        data = good_draft(**dict(zip(draft_keys, bits, strict=True)))
        audit.check(f"draft_{bits}", application_guard(data)["pass"] is all(bits))
    for stage in (None, True, 1, [], {}, "send"):
        try:
            application_guard({"stage": stage})
            ok = False
        except ValueError:
            ok = True
        audit.check(f"stage_invalid_{stage!r}", ok)

    rng = random.Random(20260825)
    base = "https://Example.com/jobs/42?a=1&b=2"
    canonical = canonical_url(base)
    tracking = ["utm_source", "utm_campaign", "gclid", "fbclid", "ref", "source"]
    for index in range(110):
        params = [
            f"{key}={rng.randint(1, 99999)}"
            for key in rng.sample(tracking, k=rng.randint(1, len(tracking)))
        ]
        variant = base + "&" + "&".join(params) + ("#section" if index % 2 else "")
        audit.check(f"canonical_tracking_{index}", canonical_url(variant) == canonical)

    reference = content_hash("Senior WordPress Developer with WooCommerce")
    for index in range(40):
        noise = " " * (index % 5 + 1)
        variant = (
            f"{noise}SENIOR{noise}WordPress Developer with WooCommerce "
            f"https://track.example/{index}{noise}"
        )
        audit.check(f"hash_noise_{index}", content_hash(variant) == reference)
    for index in range(30):
        audit.check(
            f"hash_material_{index}",
            content_hash(f"Senior WordPress Developer requirement {index}") != reference,
        )

    now = datetime.now(UTC)
    for days in (0, 1, 3, 6.999):
        item = JobRecord(
            "x",
            str(days),
            "Senior Dev",
            "Acme",
            f"https://example.com/{days}",
            posted_at=(now - timedelta(days=days)).isoformat(),
        )
        fresh, _ = filter_recency([item], 7)
        audit.check(f"recency_past_{days}", len(fresh) == 1)
    for days in (0.001, 1, 30):
        item = JobRecord(
            "x",
            f"f{days}",
            "Senior Dev",
            "Acme",
            f"https://example.com/f{days}",
            posted_at=(now + timedelta(days=days)).isoformat(),
        )
        fresh, unknown = filter_recency([item], 7)
        audit.check(f"recency_future_{days}", not fresh and not unknown)

    for index, invalid_window in enumerate((True, float("nan"), float("inf"), -float("inf"))):
        try:
            filter_recency([], invalid_window)
            ok = False
        except ValueError:
            ok = True
        audit.check(f"recency_invalid_window_{index}", ok)

    for index, url in enumerate(
        (
            "http://127.0.0.1/",
            "http://10.0.0.1/",
            "http://169.254.169.254/",
            "http://localhost/",
            "http://service.internal/",
            "http://intranet/",
            "https://example.com:8443/",
            "https://user:pass@example.com/",
        )
    ):
        try:
            validate_public_url(url)
            ok = False
        except (ValueError, RuntimeError):
            ok = True
        audit.check(f"target_block_{index}", ok)

    for index in range(30):
        country = "NL" if index % 3 == 0 else ("DE" if index % 3 == 1 else "US")
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
        "failures": audit.failures[:100],
    }


def main() -> int:
    result = run_audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
