#!/usr/bin/env python3
"""Repeatable local/CI release gate for vacature-engine."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
REQUIRED_FILES = (
    ROOT / "README.md",
    ROOT / "SECURITY.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "schemas" / "job.schema.json",
    ROOT / "src" / "vacature_engine" / "policy.py",
    ROOT / "tests" / "test_skill_parity_vectors.py",
)
ACTION_RE = re.compile(r"^\s*- uses: [^@\s]+@([0-9a-f]{40})(?:\s+#.*)?$", re.MULTILINE)


def run(cmd: list[str]) -> dict[str, object]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-ruff", action="store_true")
    args = parser.parse_args()

    checks: list[dict[str, object]] = []
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_FILES if not path.exists()]
    checks.append({"name": "required_files", "pass": not missing, "missing": missing})

    workflow = WORKFLOW.read_text(encoding="utf-8") if WORKFLOW.exists() else ""
    uses_lines = [line for line in workflow.splitlines() if "uses:" in line]
    pinned = len(ACTION_RE.findall(workflow)) == len(uses_lines) and bool(uses_lines)
    checks.append({"name": "full_sha_action_pins", "pass": pinned, "uses": uses_lines})
    checks.append({"name": "least_privilege", "pass": "permissions:\n  contents: read" in workflow})
    checks.append({"name": "explicit_timeout", "pass": "timeout-minutes:" in workflow})

    compile_result = run([sys.executable, "-m", "compileall", "-q", "src", "tests", "scripts"])
    checks.append({"name": "compile", "pass": compile_result["returncode"] == 0, **compile_result})

    test_result = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    checks.append({"name": "unit_tests", "pass": test_result["returncode"] == 0, **test_result})

    ruff = shutil.which("ruff")
    if ruff:
        lint_result = run([ruff, "check", "."])
        checks.append({"name": "ruff", "pass": lint_result["returncode"] == 0, **lint_result})
    else:
        checks.append({"name": "ruff", "pass": not args.require_ruff, "skipped": True})

    passed = all(bool(check["pass"]) for check in checks)
    print(json.dumps({"pass": passed, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
