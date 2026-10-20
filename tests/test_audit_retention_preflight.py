"""Independent contract tests for the audit-evidence backlog fix.

Use the real YAML shell command and a test-local dummy HTML renderer.
No credentials, provider requests, or Registry writes are involved.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github' / 'workflows' / 'one-pass-vacancy-review.yml'


class RetentionAndPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding='utf-8')
        name = '      - name: Render offline coverage'
        cls.assertIsNotNone(cls, cls.workflow.find(name) if name in cls.workflow else None)
        cls.section = cls.workflow.split(name, 1)[1].split('\n      - ', 1)[0]
        cls.command = textwrap.dedent(cls.section.split('        run: |\n', 1)[1])

    def _execute(self, outcome, report=None):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'scripts').mkdir()
            if report is not None:
                (root / 'vacancy-review.json').write_text(report, encoding='utf-8')
            (root / 'scripts' / 'render_source_coverage.py').write_text(
                'import sys\nfrom pathlib import Path\n'
                'Path(sys.argv[sys.argv.index("--output") + 1]).write_text("OK")\n',
                encoding='utf-8')
            run = subprocess.run(
                ['bash', '-e', '-c', self.command], cwd=root,
                env={**os.environ, 'RUNNER_TEMP': folder,
                     'DISCOVERY_OUTCOME': outcome},
                capture_output=True, text=True, timeout=10)
            marker = root / 'preflight-status.json'
            data = json.loads(marker.read_text('utf-8')) if marker.exists() else None
            return run.returncode, data, (root / 'source-coverage.html').exists(), run.stdout, run.stderr

    def test_retention_seven_days_for_evidence_review(self):
        self.assertRegex(self.workflow, r'(?m)^\s+retention-days:\s+7\s*$')

    def test_artifact_allowlist_contains_one_sanitized_preflight_marker(self):
        artifact = self.workflow.split('actions/upload-artifact@', 1)[1]
        self.assertIn('preflight-status.json', artifact)
        self.assertIn('source-coverage.html', artifact)
        self.assertIn('vacancy-review.json', artifact)
        self.assertNotIn('**', artifact)
        self.assertIn('if: ${{ always() }}', artifact)

    def test_blocked_preflight_without_report_has_auditable_status(self):
        rc, record, dashboard, stdout, _ = self._execute('failure')
        self.assertEqual(rc, 0)
        self.assertFalse(dashboard)
        self.assertIsNotNone(record)
        self.assertEqual(record['schema'], 'vacancy-preflight-status.v1')
        self.assertEqual(record['status'], 'blocked')
        self.assertEqual(record['discovery_outcome'], 'failure')
        self.assertEqual(record['full_search_report'], False)
        self.assertIn('No report produced', stdout)

    def test_missing_report_after_success_remains_failure_with_evidence(self):
        rc, record, dashboard, _, _ = self._execute('success')
        self.assertNotEqual(rc, 0)
        self.assertFalse(dashboard)
        self.assertEqual(record['status'], 'error')
        self.assertEqual(record['reason'], 'success_without_report')
        self.assertEqual(record['full_search_report'], False)

    def test_empty_report_after_success_remains_failure_with_evidence(self):
        rc, record, dashboard, _, _ = self._execute('success', '')
        self.assertNotEqual(rc, 0)
        self.assertFalse(dashboard)
        self.assertEqual(record['reason'], 'success_without_report')

    def test_original_json_remains_primary_evidence(self):
        for outcome in ('success', 'failure'):
            with self.subTest(outcome=outcome):
                rc, record, dashboard, _, _ = self._execute(outcome, '{"coverage":{}}')
                self.assertEqual(rc, 0)
                self.assertTrue(dashboard)
                self.assertIsNone(record)

    def test_unknown_outcome_is_reduced_to_safe_enum(self):
        rc, record, dashboard, _, _ = self._execute('invalid-test-<script>')
        self.assertEqual(rc, 0)
        self.assertFalse(dashboard)
        self.assertEqual(record['discovery_outcome'], 'unknown')
        self.assertNotIn('invalid-test-', json.dumps(record))

    def test_marker_does_not_include_credential_or_untrusted_fields(self):
        rc, record, _, _, _ = self._execute('skipped')
        self.assertEqual(rc, 0)
        self.assertEqual(set(record), {
            'schema', 'status', 'reason', 'discovery_outcome', 'full_search_report'})
        self.assertEqual(record['discovery_outcome'], 'skipped')

    def test_no_other_workflow_permissions_or_triggers_added(self):
        self.assertIn('workflow_dispatch:', self.workflow)
        self.assertIn('  contents: read', self.workflow)
        self.assertNotIn('contents: write', self.workflow)
        self.assertNotIn('  schedule:', self.workflow)
        self.assertNotIn('git push', self.workflow)


if __name__ == '__main__':
    unittest.main()
