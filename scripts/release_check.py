#!/usr/bin/env python3
"""Repeatable local/CI release gate for vacature-engine."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
REQUIRED_FILES = (
    ROOT / "README.md",
    ROOT / "SECURITY.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "schemas" / "job.schema.json",
    ROOT / "src" / "vacature_engine" / "policy.py",
    ROOT / "src" / "vacature_engine" / "structured.py",
    ROOT / "tests" / "test_skill_parity_vectors.py",
    ROOT / "scripts" / "scenario_audit.py",
)
ACTION_RE = re.compile(r"^\s*- uses: [^@\s]+@([0-9a-f]{40})(?:\s+#.*)?$", re.MULTILINE)
VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def run(cmd: list[str]) -> dict[str, object]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-8000:],
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

    try:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project_version = str(pyproject["project"]["version"])
        init_text = (ROOT / "src" / "vacature_engine" / "__init__.py").read_text(encoding="utf-8")
        match = VERSION_RE.search(init_text)
        package_version = match.group(1) if match else None
        version_ok = package_version == project_version and package_version is not None
        checks.append(
            {
                "name": "version_consistency",
                "pass": version_ok,
                "pyproject": project_version,
                "package": package_version,
            }
        )
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        checks.append({"name": "version_consistency", "pass": False, "error": str(exc)})

    try:
        schema = json.loads((ROOT / "schemas" / "job.schema.json").read_text(encoding="utf-8"))
        checks.append(
            {
                "name": "schema_contract",
                "pass": schema.get("additionalProperties") is False
                and "source_date" in schema.get("properties", {})
                and "vacancy_id" in schema.get("required", []),
            }
        )
    except (OSError, json.JSONDecodeError) as exc:
        checks.append({"name": "schema_contract", "pass": False, "error": str(exc)})

    compile_result = run([sys.executable, "-m", "compileall", "-q", "src", "tests", "scripts"])
    checks.append({"name": "compile", "pass": compile_result["returncode"] == 0, **compile_result})

    test_result = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    checks.append({"name": "unit_tests", "pass": test_result["returncode"] == 0, **test_result})

    scenario_result = run([sys.executable, "scripts/scenario_audit.py"])
    scenario_pass = scenario_result["returncode"] == 0
    scenario_count = None
    try:
        scenario_payload = json.loads(str(scenario_result["stdout"]))
        scenario_count = scenario_payload.get("scenario_count")
    except json.JSONDecodeError:
        pass
    checks.append(
        {
            "name": "scenario_audit",
            "pass": scenario_pass,
            "scenario_count": scenario_count,
            **scenario_result,
        }
    )

    if args.require_ruff:
        lint_result = run([sys.executable, "-m", "ruff", "check", "."])
        checks.append(
            {
                "name": "ruff",
                "pass": lint_result["returncode"] == 0,
                "required": True,
                **lint_result,
            }
        )
    else:
        lint_result = run([sys.executable, "-m", "ruff", "check", "."])
        if lint_result["returncode"] == 0:
            checks.append({"name": "ruff", "pass": True, "required": False, **lint_result})
        elif "No module named ruff" in str(lint_result["stderr"]):
            checks.append({"name": "ruff", "pass": True, "required": False, "skipped": True})
        else:
            checks.append({"name": "ruff", "pass": False, "required": False, **lint_result})

    passed = all(bool(check["pass"]) for check in checks)
    print(json.dumps({"pass": passed, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
