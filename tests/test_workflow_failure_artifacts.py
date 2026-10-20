"""Source-contract regression: blocked vacancy run must retain available audit files.

Standard library only; suitable for the existing root unittest discovery.
"""
from __future__ import annotations

import re
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parents[1] / ".github" / "workflows" /
            "one-pass-vacancy-review.yml")


class WorkflowFailureArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    @staticmethod
    def _section(text: str, name: str) -> str:
        marker = "      - name: " + name
        if marker not in text:
            raise AssertionError("Missing workflow section: " + name)
        return text.split(marker, 1)[1].split("\n      - ", 1)[0]

    def test_audit_render_runs_after_discovery_failure(self):
        s = self._section(self.text, "Render offline coverage")
        self.assertIn("if: ${{ always() }}", s)
        self.assertIn("vacancy-review.json", s)

    def test_missing_report_is_not_fabricated(self):
        s = self._section(self.text, "Render offline coverage")
        self.assertIn('if [ -s "$RUNNER_TEMP/vacancy-review.json" ]; then', s)
        self.assertIn("No report produced", s)

    def test_uploader_runs_even_when_discovery_failed(self):
        s = self.text.split("actions/upload-artifact@", 1)[1]
        self.assertIn("if: ${{ always() }}", s)
        self.assertIn("if-no-files-found: warn", s)

    def test_upload_is_only_two_audit_files(self):
        s = self.text.split("actions/upload-artifact@", 1)[1]
        self.assertIn("vacancy-review.json", s)
        self.assertIn("source-coverage.html", s)
        self.assertNotIn("**", s)
        self.assertNotIn("secret", s.lower())

    def test_manual_and_read_only_security_unchanged(self):
        self.assertIn("workflow_dispatch:", self.text)
        self.assertNotIn("\n  schedule:", self.text)
        self.assertIn("  contents: read", self.text)
        self.assertNotIn("contents: write", self.text)
        self.assertNotIn("git push", self.text)

    def test_discovery_outcome_is_exposed_to_report_guard(self):
        s = self._section(self.text, "Run Register-gated")
        self.assertIn("id: discovery", s)
        dashboard = self._section(self.text, "Render offline coverage")
        self.assertIn("steps.discovery.outcome", dashboard)
        self.assertIn("exit 1", dashboard)

    @classmethod
    def _render_command(cls, outcome):
        section = cls._section(cls.text, "Render offline coverage")
        command = section.split("        run: |\n", 1)[1]
        return textwrap.dedent(command).replace(
            "${{ steps.discovery.outcome }}", outcome)

    @classmethod
    def _shell_case(cls, outcome, present=False, empty=False, renderer_fails=False):
        with tempfile.TemporaryDirectory() as td:
            from pathlib import Path
            root = Path(td)
            (root / "scripts").mkdir()
            json_path = root / "vacancy-review.json"
            if present:
                json_path.write_text("" if empty else '{"coverage": {}}')
            (root / "scripts" / "render_source_coverage.py").write_text(
                'import sys\nfrom pathlib import Path\n'
                + ('raise RuntimeError("broken-renderer")\n' if renderer_fails else
                   'Path(sys.argv[sys.argv.index("--output")+1]).write_text("dashboard")\n'))
            cp = subprocess.run(
                ["bash", "-e", "-c", cls._render_command(outcome)],
                cwd=root, env={**os.environ, "RUNNER_TEMP": str(root),
                     "DISCOVERY_OUTCOME": outcome},
                capture_output=True, text=True, timeout=10)
            return cp.returncode, cp.stdout, cp.stderr, (
                root / "source-coverage.html").exists(), json_path.exists()

    def test_success_without_report_is_hard_failure(self):
        status, stdout, _, exists, _ = self._shell_case("success")
        self.assertNotEqual(status, 0)
        self.assertIn("::error::", stdout)
        self.assertFalse(exists)

    def test_success_with_empty_report_is_hard_failure(self):
        status, stdout, _, exists, _ = self._shell_case(
            "success", present=True, empty=True)
        self.assertNotEqual(status, 0)
        self.assertIn("::error::", stdout)
        self.assertFalse(exists)

    def test_blocked_preflight_without_report_is_not_fabricated(self):
        status, stdout, _, exists, had_json = self._shell_case("failure")
        self.assertEqual(status, 0)
        self.assertIn("No report produced", stdout)
        self.assertFalse(exists)
        self.assertFalse(had_json)

    def test_blocked_discovery_preserves_real_report_and_renders(self):
        status, _, err, exists, had_json = self._shell_case(
            "failure", present=True)
        self.assertEqual(status, 0, err)
        self.assertTrue(exists)
        self.assertTrue(had_json)

    def test_renderer_failure_does_not_delete_json_or_mask_error(self):
        status, _, stderr, exists, had_json = self._shell_case(
            "failure", present=True, renderer_fails=True)
        self.assertNotEqual(status, 0)
        self.assertIn("broken-renderer", stderr)
        self.assertFalse(exists)
        self.assertTrue(had_json)

    def test_successful_discovery_keeps_both_reports(self):
        status, _, stderr, exists, had_json = self._shell_case(
            "success", present=True)
        self.assertEqual(status, 0, stderr)
        self.assertTrue(exists)
        self.assertTrue(had_json)

    def test_failures_not_suppressed(self):
        self.assertNotIn("|| true", self.text)
        self.assertNotIn("set +e", self.text)
        self.assertIn('python scripts/one_pass_vacancies.py', self.text)


if __name__ == "__main__":
    unittest.main()
