"""Reproducible quarter-hour rollup validation: coverage, dedupe and fail-closed."""
import importlib.util
import io
import json
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / 'radar' / 'scripts' / 'hourly_rollup.py'
SPEC = importlib.util.spec_from_file_location('hourly_rollup', HERE)
rollup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rollup)


class HourlyRollupTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
        self.runs = [
            {'id': i, 'name': rollup.WORKFLOW_NAME, 'event': 'schedule',
             'head_branch': 'main', 'status': 'completed', 'conclusion': 'success',
             'created_at': f'2026-10-18T12:{minute:02d}:00Z'}
            for i, minute in enumerate([6, 21, 36, 51], 1)
        ]
        self.scope = {'technical_source_scope': {'supported': 13}}
        self.payload = {
            'status': 'review_ready', 'mode': 'read_only',
            'manual_review_required': True, 'google_sheet_rows_written': 0,
            'application_submissions': 0, 'failures': [],
            'counts': {'observed': 711, 'review_candidates': 1,
                       'previously_seen': 0, 'already_in_register': 0,
                       'previously_applied': 0},
            'candidates': [{'observation_key': 'ashby:zapier:123',
                            'official_url': 'https://jobs.ashbyhq.com/zapier/123',
                            'title': 'Automation Engineer', 'employer': 'Zapier',
                            'verification': 'manual review required'}],
        }

    def summary(self, runs=None, artifacts=None):
        return rollup.summarize(
            self.runs if runs is None else runs,
            {i: (self.scope, self.payload) for i in range(1, 5)}
            if artifacts is None else artifacts,
            self.start, self.start + timedelta(hours=1),
        )

    def test_four_scheduled_dedupe_without_inventing_verified_matches(self):
        result = self.summary()
        self.assertEqual(result['status'], 'coverage_complete')
        self.assertEqual(result['validated_successful_quarter_checks'], 4)
        self.assertEqual(result['observations_scanned_across_valid_runs'], 2844)
        self.assertEqual(result['unique_unverified_review_candidates'], 1)
        self.assertEqual(result['repeated_candidates_within_hour'], 3)
        self.assertEqual(result['verified_eligible_vacancies'], [])

    def test_four_runs_in_same_slot_are_not_four_valid_quarters(self):
        runs = [dict(r, created_at=f'2026-10-18T12:{8+i:02d}:00Z')
                for i, r in enumerate(self.runs)]
        result = self.summary(runs)
        self.assertEqual(result['actual_schedule_events'], 4)
        self.assertEqual(result['missing_or_unattributed_quarter_slots'], 3)
        self.assertEqual(result['status'], 'coverage_incomplete')

    def test_missing_quarters_are_unknown_not_zero(self):
        result = self.summary(self.runs[:1], {1: (self.scope, self.payload)})
        self.assertEqual(result['missing_or_late_events'], 3)
        self.assertEqual(result['status'], 'coverage_incomplete')

    def test_failed_quarter_is_not_counted_as_success(self):
        bad = [dict(self.runs[0], conclusion='failure'), *self.runs[1:]]
        result = self.summary(bad)
        self.assertEqual(result['failed_or_unverified_runs'], 1)
        self.assertEqual(result['validated_successful_quarter_checks'], 3)

    def test_partial_artifact_is_never_accepted(self):
        partial = dict(self.payload, status='partial')
        result = self.summary(artifacts={
            i: (self.scope, partial if i == 2 else self.payload)
            for i in range(1, 5)
        })
        self.assertEqual(result['status'], 'coverage_incomplete')
        self.assertEqual(result['runs'][1]['status'], 'artifact_invalid')

    def test_issue_and_dispatch_runs_are_never_falsely_scheduled(self):
        result = self.summary([dict(x, event='issues') for x in self.runs], {})
        self.assertEqual(result['actual_schedule_events'], 0)
        self.assertEqual(result['missing_or_late_events'], 4)

    def test_zip_roundtrip(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('scheduled-observations.log', '\n'.join(
                json.dumps(x) for x in (self.scope, self.payload)) + '\n')
        scope, payload = rollup.read_artifact_zip(buffer.getvalue())
        self.assertEqual(rollup.valid_result(scope, payload)[0]['observed'], 711)

    def test_untrusted_http_job_url_is_rejected(self):
        candidate = dict(self.payload['candidates'][0],
                         official_url='http://evil.test')
        bad = dict(self.payload, candidates=[candidate])
        with self.assertRaises(ValueError):
            rollup.valid_result(self.scope, bad)

    def test_writes_and_claimed_verification_rejected(self):
        for change in [{'google_sheet_rows_written': 1},
                       {'application_submissions': 1},
                       {'manual_review_required': False}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                rollup.valid_result(self.scope, dict(self.payload, **change))

    def test_period_is_completed_previous_utc_hour(self):
        begin, end = rollup.period(datetime(2026, 10, 18, 13, 5,
                                            tzinfo=timezone.utc))
        self.assertEqual((begin, end),
                         (self.start, self.start + timedelta(hours=1)))

    def test_reject_second_zip_file(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('scheduled-observations.log', '{}\n{}\n')
            archive.writestr('extra.txt', 'bad')
        with self.assertRaises(ValueError):
            rollup.read_artifact_zip(buffer.getvalue())

    def test_repository_and_workflow_bound(self):
        self.assertEqual(rollup.WORKFLOW_NAME,
                         'Vacature Radar quarter-hour observations')
        self.assertTrue(rollup.API_ROOT.startswith(
            'https://api.github.com/repos/'))

if __name__ == '__main__':
    unittest.main()
