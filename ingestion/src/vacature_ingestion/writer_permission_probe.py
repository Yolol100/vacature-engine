"""One-time fail-closed permission probe of the existing Sheets writer.

Owner-only GitHub issue trigger; writes back exactly the value it just read.
Never edits policy, source identities, application records or submission state.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import quote

from .register_sync import _request_json, _service_account_token

REGISTER_ID = '1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0'
EXPECTED_EMAIL = 'vacature-radar@leads-507621.iam.gserviceaccount.com'
CELL = 'Bronnen!G2'
WORKFLOW = 'Vacature Register writer permission probe'
COMMAND = '[ingestion] writer 403 probe'


def prove_without_data_change(credentials, request_json=_request_json, token_fn=_service_account_token):
    if not isinstance(credentials, dict) or credentials.get('client_email') != EXPECTED_EMAIL:
        raise ValueError('Unexpected Google service account identity')
    token = token_fn(credentials)
    base = f'https://sheets.googleapis.com/v4/spreadsheets/{REGISTER_ID}'
    encoded_cell = quote(CELL, safe='!')
    url = f'{base}/values/{encoded_cell}'
    initial = request_json(url, token, method='GET')
    values = initial.get('values') if isinstance(initial, dict) else None
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], list) or len(values[0]) != 1:
        raise ValueError('Unexpected probe cell shape')
    existing = values[0][0]
    if not isinstance(existing, str) or not (15 <= len(existing) <= 45):
        raise ValueError('Unexpected source-health timestamp')
    if datetime.fromisoformat(existing.replace('Z', '+00:00')).tzinfo is None:
        raise ValueError('Unzoned source-health timestamp')
    # Two reads provide a cheap guard against a concurrent source-health edit.
    repeat = request_json(url, token, method='GET')
    if repeat.get('values') != [[existing]]:
        raise ValueError('Concurrent source-health change; probe aborted')
    # Write exactly the pre-existing value to the same exact cell. No business
    # contents change and all cell formatting and validation are preserved.
    outcome = request_json(url + '?valueInputOption=RAW', token, method='PUT',
                           body={'range': CELL, 'majorDimension': 'ROWS',
                                 'values': [[existing]]})
    if not isinstance(outcome, dict) or outcome.get('updatedCells') != 1:
        raise ValueError('Writer probe did not confirm exactly one updated cell')
    final = request_json(url, token, method='GET')
    if final.get('values') != [[existing]]:
        raise ValueError('Writer probe readback mismatch')
    return {'status': 'pass', 'writer_scope_confirmed': True,
            'same_cell_value_readback': True,
            'application_submissions': 0, 'changed_business_values': 0}


def main():
    env = os.environ
    if (env.get('GITHUB_REPOSITORY') != 'Yolol100/vacature-engine' or
            env.get('GITHUB_WORKFLOW') != WORKFLOW or
            env.get('GITHUB_EVENT_NAME') != 'issues' or
            env.get('GITHUB_ACTOR') != 'Yolol100' or
            env.get('PROBE_ISSUE_TITLE') != COMMAND or
            env.get('PROBE_ISSUE_OWNER') != 'Yolol100'):
        raise ValueError('Unauthorized service-account permission probe')
    credentials = json.loads(env.get('GOOGLE_SERVICE_ACCOUNT_JSON') or '{}')
    print(json.dumps(prove_without_data_change(credentials), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        message = 'Writer permission probe failed: ' + type(exc).__name__
        if isinstance(exc, HTTPError):
            message += ' HTTP' + str(exc.code)
        print(message, file=sys.stderr)
        sys.exit(1)
