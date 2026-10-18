"""Fail-closed tests for isolated owner-authorized Google writer permission probe."""
from __future__ import annotations

import unittest
from urllib.error import HTTPError

from vacature_ingestion.writer_permission_probe import (
    CELL, EXPECTED_EMAIL, REGISTER_ID, prove_without_data_change,
)


class WriterPermissionProbeTests(unittest.TestCase):
    def setUp(self):
        self.value = "2026-09-20T23:06:05.377Z"
        self.credentials = {'client_email': EXPECTED_EMAIL, 'private_key': 'unused in mock'}
        self.calls = []

    def request(self, url, token, *, method='GET', body=None):
        self.calls.append((method, url, body))
        self.assertEqual(token, "mock-writer-token")
        self.assertIn(REGISTER_ID, url)
        self.assertIn(CELL, url)
        if method == "PUT":
            self.assertEqual(url.split("?")[-1], "valueInputOption=RAW")
            self.assertEqual(body, {'range': CELL, 'majorDimension': 'ROWS',
                                    'values': [[self.value]]})
            return {'updatedCells': 1}
        self.assertEqual(method, "GET")
        self.assertIsNone(body)
        return {'values': [[self.value]]}

    def token(self, credentials):
        self.assertEqual(credentials['client_email'], EXPECTED_EMAIL)
        return "mock-writer-token"

    def test_success_replays_the_exact_original_value(self):
        out = prove_without_data_change(
            self.credentials, request_json=self.request, token_fn=self.token)
        self.assertEqual(out['status'], 'pass')
        self.assertEqual(out['changed_business_values'], 0)
        self.assertEqual(out['application_submissions'], 0)
        self.assertEqual([call[0] for call in self.calls],
                         ['GET', 'GET', 'PUT', 'GET'])

    def test_refuses_unexpected_service_account(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected Google service account'):
            prove_without_data_change({'client_email': 'attacker@example.test'},
                                      request_json=self.request, token_fn=self.token)
        self.assertEqual(self.calls, [])

    def test_refuses_edited_cell_between_reads(self):
        def concurrent(url, token, *, method='GET', body=None):
            if len(self.calls) == 1:
                self.value = '2026-09-20T23:06:05.378Z'
            return self.request(url, token, method=method, body=body)
        with self.assertRaisesRegex(ValueError, 'Concurrent source-health'):
            prove_without_data_change(self.credentials,
                                      request_json=concurrent, token_fn=self.token)
        self.assertEqual(len([c for c in self.calls if c[0] == 'PUT']), 0)

    def test_refuses_missing_timestamp(self):
        self.value = ''
        with self.assertRaisesRegex(ValueError, 'Unexpected source-health timestamp'):
            prove_without_data_change(self.credentials,
                                      request_json=self.request, token_fn=self.token)
        self.assertEqual([c[0] for c in self.calls], ['GET'])

    def test_refuses_unzoned_timestamp(self):
        self.value = '2026-09-20T23:06:05.377'
        with self.assertRaisesRegex(ValueError, 'Unzoned source-health'):
            prove_without_data_change(self.credentials,
                                      request_json=self.request, token_fn=self.token)
        self.assertEqual([c[0] for c in self.calls], ['GET'])

    def test_refuses_non_single_cell_response(self):
        self.value = '2026-09-20T23:06:05.377Z'
        def malformed(*args, **kwargs):
            return {'values': [['a', 'b']]}
        with self.assertRaisesRegex(ValueError, 'Unexpected probe cell shape'):
            prove_without_data_change(self.credentials,
                                      request_json=malformed, token_fn=self.token)

    def test_preserves_authorized_http_errors(self):
        def forbidden(url, token, *, method='GET', body=None):
            if method == 'PUT':
                raise HTTPError(url, 403, 'Forbidden', {}, None)
            return self.request(url, token, method=method, body=body)
        with self.assertRaises(HTTPError) as ctx:
            prove_without_data_change(self.credentials,
                                      request_json=forbidden, token_fn=self.token)
        self.assertEqual(ctx.exception.code, 403)
        self.assertEqual([c[0] for c in self.calls], ['GET', 'GET'])

    def test_requires_exact_updated_cells(self):
        def bad_response(url, token, *, method='GET', body=None):
            if method == 'PUT':
                return {'updatedCells': 0}
            return self.request(url, token, method=method, body=body)
        with self.assertRaisesRegex(ValueError, 'exactly one updated cell'):
            prove_without_data_change(self.credentials,
                                      request_json=bad_response, token_fn=self.token)


if __name__ == '__main__':
    unittest.main()
