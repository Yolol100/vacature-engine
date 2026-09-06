#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = Path("src/vacature_engine/simple.py")
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
        "wordpress-hard-gate",
        'if vacancy.get("wordpress_related") is not True:',
        'if vacancy.get("wordpress_related") is True:',
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


def run_tests(root: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_simple.py", "-v"],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def main() -> int:
    baseline = run_tests(ROOT)
    if baseline.returncode != 0:
        print("Baseline tests are red; mutation smoke cannot run.")
        print(baseline.stdout)
        return 2

    survived: list[str] = []
    for name, old, new in MUTANTS:
        with tempfile.TemporaryDirectory(prefix="vacature-mutant-") as temp:
            target_root = Path(temp) / "repo"
            shutil.copytree(ROOT, target_root, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
            source_path = target_root / TARGET
            source = source_path.read_text(encoding="utf-8")
            if source.count(old) != 1:
                print(f"Mutation {name} is stale: expected one target, found {source.count(old)}")
                return 3
            source_path.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")
            result = run_tests(target_root)
            if result.returncode == 0:
                survived.append(name)
                print(f"SURVIVED: {name}")
            else:
                print(f"KILLED: {name}")

    if survived:
        print("Surviving mutations: " + ", ".join(survived))
        return 1
    print(f"All {len(MUTANTS)} controlled mutations were killed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
