"""Read-only hourly rollup of four genuine quarter-hour GitHub Actions observations.

Neither discovery candidates nor GitHub success are proof of eligible vacancies.
All applicants, email sending, and writing to business Google Sheets stay out of scope.
"""
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

API_ROOT = 'https://api.github.com/repos/Yolol100/vacature-engine'
WORKFLOW_NAME = 'Vacature Radar quarter-hour observations'
MAX_ARTIFACT_BYTES = 200_000
MAX_GH_BODY = 1_000_000
MAX_CANDIDATES_PER_RUN = 10
MAX_RUNS_PER_HOUR = 8

def parse_utc(value):
    if not isinstance(value, str):
        raise ValueError('Invalid UTC timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Unzoned timestamp')
    return parsed.astimezone(timezone.utc)

def period(now):
    end = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return end - timedelta(hours=1), end

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def _bounded_body(response, limit):
    data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Oversized GitHub response')
    return data

def gh_request(path, token, binary=False):
    if not path.startswith(API_ROOT + '/'):
        raise ValueError('Unexpected GitHub API endpoint')
    req = urllib.request.Request(path, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'webactueel-readonly-vacature-hourly',
    })
    # Explicitly prevent GitHub API Authorization leaking to artifact-storage
    # hosts through the default urllib redirect handler.
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=20) as response:
            raw = _bounded_body(response, MAX_ARTIFACT_BYTES if binary else MAX_GH_BODY)
    except urllib.error.HTTPError as err:
        if not binary or err.code not in (301, 302, 303, 307, 308):
            raise
        signed_url = err.headers.get('Location', '')
        destination = urlsplit(signed_url)
        if (destination.scheme != 'https' or not destination.hostname
                or destination.username or destination.password
                or destination.hostname.lower() == 'api.github.com'):
            raise ValueError('Unsafe artifact redirect')
        anonymous = urllib.request.Request(signed_url, headers={
            'Accept': 'application/zip',
            'User-Agent': 'webactueel-readonly-vacature-hourly',
        })
        with urllib.request.urlopen(anonymous, timeout=20) as response:
            raw = _bounded_body(response, MAX_ARTIFACT_BYTES)
    if binary:
        return raw
    if len(raw) > MAX_GH_BODY:
        raise ValueError('Oversized GitHub API response')
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError('Invalid GitHub API response')
    return data

def read_artifact_zip(blob):
    if len(blob) > MAX_ARTIFACT_BYTES:
        raise ValueError('Oversized quarter-hour artifact')
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.namelist()
        if names != ['scheduled-observations.log']:
            raise ValueError('Unexpected artifact members')
        info = archive.getinfo(names[0])
        if info.file_size > MAX_ARTIFACT_BYTES:
            raise ValueError('Oversized unpacked observations')
        lines = archive.read(names[0]).decode('utf-8').strip().splitlines()
    if len(lines) != 2:
        raise ValueError('Unexpected observation record count')
    scope, evidence = [json.loads(line) for line in lines]
    if not isinstance(scope, dict) or not isinstance(evidence, dict):
        raise ValueError('Invalid observation JSON')
    return scope, evidence

def valid_result(scope, data):
    technical = scope.get('technical_source_scope')
    if not isinstance(technical, dict) or not isinstance(technical.get('supported'), int):
        raise ValueError('Technical source count missing')
    if technical['supported'] < 1 or technical['supported'] > 30:
        raise ValueError('Unexpected source count')
    if (data.get('status') != 'review_ready' or data.get('mode') != 'read_only'
            or data.get('manual_review_required') is not True
            or data.get('google_sheet_rows_written') != 0
            or data.get('application_submissions') != 0 or data.get('failures') != []):
        raise ValueError('Failed, partial or writing quarter-hour evidence')
    counts, candidates = data.get('counts'), data.get('candidates')
    if (not isinstance(counts, dict) or not isinstance(candidates, list)
            or len(candidates) > MAX_CANDIDATES_PER_RUN):
        raise ValueError('Malformed technical counts')
    for key in ('observed', 'review_candidates', 'previously_seen',
                'already_in_register', 'previously_applied'):
        value = counts.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError('Invalid technical count')
    if counts['review_candidates'] != len(candidates):
        raise ValueError('Inconsistent review candidate count')
    for c in candidates:
        if (not isinstance(c, dict) or
                any(not isinstance(c.get(k), str) for k in
                    ('observation_key', 'official_url', 'title', 'employer', 'verification'))):
            raise ValueError('Invalid candidate record')
        url = urlsplit(c['official_url'])
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or len(c['official_url']) > 500 or len(c['title']) > 240
                or len(c['employer']) > 160 or len(c['observation_key']) > 200
                or 'manual' not in c['verification'].lower()):
            raise ValueError('Unsafe or falsely verified technical candidate')
    return counts, candidates

def summarize(runs, artifacts_by_run, start, end):
    """Group observed schedule-run timestamps; they may be delayed by GitHub."""
    included = []
    for run in runs:
        try:
            created = parse_utc(run['created_at'])
        except (ValueError, KeyError, TypeError):
            continue
        if (start <= created < end and run.get('name') == WORKFLOW_NAME
                and run.get('event') == 'schedule' and run.get('head_branch') == 'main'):
            included.append(run)
    included.sort(key=lambda r: r['created_at'])
    if len(included) > MAX_RUNS_PER_HOUR:
        raise ValueError('Unexpected excess of scheduled runs')
    outcomes, unique, urls = [], {}, set()
    duplicates = observed_total = 0
    for run in included:
        run_id = run.get('id')
        if not isinstance(run_id, int):
            raise ValueError('Invalid run identifier')
        out = {'run_id': run_id, 'created_at_utc': run['created_at']}
        if run.get('status') != 'completed' or run.get('conclusion') != 'success':
            out['status'] = 'failed_or_incomplete'
        elif run_id not in artifacts_by_run:
            out['status'] = 'artifact_missing'
        else:
            try:
                artifact = artifacts_by_run[run_id]
                if isinstance(artifact, Exception):
                    raise artifact
                counts, candidates = valid_result(*artifact)
                observed_total += counts['observed']
                out.update(status='ok', sources_observed=counts['observed'],
                           technical_review_candidates=len(candidates))
                for c in candidates:
                    identity, url = c['observation_key'], c['official_url']
                    if identity in unique or url in urls:
                        duplicates += 1
                        continue
                    urls.add(url)
                    unique[identity] = {
                        'observation_key': identity, 'employer': c['employer'],
                        'title': c['title'], 'official_url': url,
                        'verified_eligible': False, 'verification_required': True,
                    }
            except (ValueError, KeyError, TypeError) as exc:
                out['status'] = 'artifact_invalid'
                out['error_category'] = type(exc).__name__
        outcomes.append(out)
    passed = sum(x['status'] == 'ok' for x in outcomes)
    failed = len(outcomes) - passed
    # A delayed/replayed schedule event must not masquerade as a different
    # quarter merely because the hour contains four distinct run IDs.
    expected_minute_bins = (6, 21, 36, 51)
    distinct_bins = set()
    for run in included:
        minute = parse_utc(run['created_at']).minute
        for slot in reversed(expected_minute_bins):
            if minute >= slot:
                distinct_bins.add(slot)
                break
    missing_bins = len(expected_minute_bins) - len(distinct_bins)
    return {
        'schema_version': 1,
        'status': 'coverage_complete' if passed == len(included) == 4 and missing_bins == 0 else 'coverage_incomplete',
        'policy': 'official_ats_technical_observation_only',
        'window_start_utc': start.isoformat().replace('+00:00', 'Z'),
        'window_end_utc': end.isoformat().replace('+00:00', 'Z'),
        'expected_quarter_checks': 4,
        'actual_schedule_events': len(included),
        'validated_successful_quarter_checks': passed,
        'failed_or_unverified_runs': failed,
        'missing_or_late_events': max(0, 4 - len(included)),
        'missing_or_unattributed_quarter_slots': missing_bins,
        'observations_scanned_across_valid_runs': observed_total,
        'unique_unverified_review_candidates': len(unique),
        'repeated_candidates_within_hour': duplicates,
        'verified_eligible_vacancies': [],
        'candidate_review_queue': list(unique.values()),
        'runs': outcomes,
        'notes': [
            'Run created_at is an observation timestamp, not a guaranteed cron slot.',
            'Missing, late and incomplete checks are UNKNOWN, never zero vacancies.',
            'ATS candidates require employer, remote-in-NL, language and fit verification.',
            'No Sheets writes, application submission or user notification performed.',
        ],
    }

def main():
    token = os.environ.get('GITHUB_TOKEN', '')
    event = os.environ.get('GITHUB_EVENT_NAME', '')
    if not token or event not in ('schedule', 'workflow_dispatch', 'issues'):
        raise ValueError('Missing read-only GitHub run credentials')
    if os.environ.get('GITHUB_REPOSITORY') != 'Yolol100/vacature-engine':
        raise ValueError('Unexpected repository')
    if event in ('issues', 'workflow_dispatch'):
        if os.environ.get('GITHUB_ACTOR') != 'Yolol100':
            raise ValueError('Unauthorized hourly evidence request')
        if event == 'issues' and os.environ.get('RADAR_ISSUE_TITLE') != '[radar] hourly evidence':
            raise ValueError('Unauthorized hourly issue request')
    start, end = period(datetime.now(timezone.utc))
    endpoint = API_ROOT + '/actions/workflows/vacature-quarter-hour.yml/runs?event=schedule&per_page=100'
    runs = gh_request(endpoint, token).get('workflow_runs')
    if not isinstance(runs, list):
        raise ValueError('Invalid workflow run listing')
    artifacts = {}
    for run in runs:
        try:
            created = parse_utc(run['created_at'])
        except (ValueError, KeyError, TypeError):
            continue
        if not (start <= created < end and run.get('name') == WORKFLOW_NAME
                and run.get('event') == 'schedule' and run.get('head_branch') == 'main'
                and run.get('status') == 'completed' and run.get('conclusion') == 'success'):
            continue
        run_id = run.get('id')
        if not isinstance(run_id, int):
            raise ValueError('Invalid scheduled run ID')
        try:
            items = gh_request(API_ROOT + f'/actions/runs/{run_id}/artifacts?per_page=40', token).get('artifacts')
            if not isinstance(items, list):
                raise ValueError('Invalid artifact listing')
            matches = [x for x in items if x.get('name') == f'radar-observations-{run_id}'
                       and not x.get('expired')]
            if len(matches) != 1:
                raise ValueError('Missing unique observation artifact')
            artifact_id = matches[0].get('id')
            if not isinstance(artifact_id, int):
                raise ValueError('Invalid artifact ID')
            archive = gh_request(API_ROOT + f'/actions/artifacts/{artifact_id}/zip',
                                 token, binary=True)
            artifacts[run_id] = read_artifact_zip(archive)
        except (ValueError, KeyError, TypeError, urllib.error.HTTPError,
                urllib.error.URLError, zipfile.BadZipFile) as exc:
            artifacts[run_id] = ValueError(type(exc).__name__)
    report = summarize(runs, artifacts, start, end)
    output = Path('.runtime/hourly-rollup.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, separators=(',', ':')) + '\n',
                      encoding='utf-8')
    print(json.dumps({k: report[k] for k in (
        'status', 'window_start_utc', 'window_end_utc',
        'actual_schedule_events', 'validated_successful_quarter_checks',
        'failed_or_unverified_runs', 'missing_or_late_events',
        'unique_unverified_review_candidates')}, sort_keys=True))

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Hourly rollup failed safely: ' + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
