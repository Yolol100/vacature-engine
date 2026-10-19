#!/usr/bin/env python3
from __future__ import annotations

import ast
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = Path("src/vacature_engine/simple.py")
VERIFIED_TARGET = Path("ingestion/src/vacature_ingestion/final_review.py")
MUTANTS = [
    (
        "unlimited-age-zero",
        "elif runtime_policy.max_posting_age_days > 0 and age_days > runtime_policy.max_posting_age_days:",
        "elif age_days > runtime_policy.max_posting_age_days:",
    ),
    (
        "remote-hard-gate",
        'if vacancy.get("fully_remote") is not True:',
        'if vacancy.get("fully_remote") is True:',
    ),
    (
        "geography-hard-gate",
        'if vacancy.get("geography_compatible") is not True:',
        'if vacancy.get("geography_compatible") is True:',
    ),
    (
        "target-role-family-hard-gate",
        "if not vacancy_role_families.intersection(runtime_policy.target_role_families):",
        "if vacancy_role_families.intersection(runtime_policy.target_role_families):",
    ),
    (
        "score-boundary",
        'ranked["score"] < runtime_policy.min_output_score',
        'ranked["score"] <= runtime_policy.min_output_score',
    ),
    (
        "core-boundary",
        "core_fit < runtime_policy.min_core_fit",
        "core_fit <= runtime_policy.min_core_fit",
    ),
    (
        "evidence-boundary",
        "evidence_fit < runtime_policy.min_evidence_fit",
        "evidence_fit <= runtime_policy.min_evidence_fit",
    ),
    (
        "salary-advisory",
        'return True, "salary_below_preference" if exact < minimum else None',
        'return True, "salary_below_preference" if exact > minimum else None',
    ),
    (
        "salary-order",
        'return (known_salary + unknown_salary)[: runtime_policy.max_output_roles]',
        'return (unknown_salary + known_salary)[: runtime_policy.max_output_roles]',
    ),
]
VERIFIED_MUTANTS = [
    (
        "verified-current-context",
        "if any(assessment.get(k) != v for k, v in context.items()):",
        "if False:",
    ),
    (
        "verified-candidate-evidence",
        'if req["outcome"] != "unknown" and (not supported or not _text(req.get("rationale"))):',
        "if False:",
    ),
    (
        "verified-mandatory-unknown",
        'if req["outcome"] == "unknown":',
        "if False:",
    ),
    (
        "verified-anchor-dimension",
        'or not any(requirement_index[r]["kind"] in dimensions for r in refs)):',
        'or False):',
    ),
]


def run_tests(root: Path, pattern: str = "test_simple.py") -> subprocess.CompletedProcess[str]:
    # Both editable packages must resolve inside the isolated mutant copy.
    # Otherwise an ingestion mutation could silently test the original package.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(
        (str(root / "src"), str(root / "ingestion/src"))),
        "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def main() -> int:
    cases = [(name, TARGET, "test_simple.py", old, new) for name, old, new in MUTANTS]
    cases.extend((name, VERIFIED_TARGET, "test_verified_gate_mutations.py", old, new)
                 for name, old, new in VERIFIED_MUTANTS)
    survived: list[str] = []
    with tempfile.TemporaryDirectory(prefix="vacature-mutant-") as temp:
        # Freeze a single baseline so concurrent workspace changes cannot make
        # a mutant appear killed by an unrelated edit. Git data is unnecessary.
        baseline_root = Path(temp) / "baseline"
        shutil.copytree(ROOT, baseline_root, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".pytest_cache"))
        for pattern in sorted({case[2] for case in cases}):
            baseline = run_tests(baseline_root, pattern)
            if baseline.returncode != 0:
                print(f"Baseline {pattern} is red; mutation smoke cannot run.")
                print(baseline.stdout)
                return 2
        for name, target, pattern, old, new in cases:
            target_root = Path(temp) / name
            shutil.copytree(baseline_root, target_root)
            source_path = target_root / target
            source = source_path.read_text(encoding="utf-8")
            if source.count(old) != 1:
                print(f"Mutation {name} is stale: expected one target, found {source.count(old)}")
                return 3
            mutated = source.replace(old, new, 1)
            ast.parse(mutated, filename=str(target))
            source_path.write_text(mutated, encoding="utf-8", newline="\n")
            result = run_tests(target_root, pattern)
            if result.returncode == 0:
                survived.append(name)
                print(f"SURVIVED: {name}")
            else:
                print(f"KILLED: {name}")

    if survived:
        print("Surviving mutations: " + ", ".join(survived))
        return 1
    print(f"All {len(cases)} controlled mutations were killed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
