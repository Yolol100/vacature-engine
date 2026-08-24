import io
import json
import unittest
from urllib.error import HTTPError

from vacature_engine.errors import FailureCategory, VacancyEngineError
from vacature_engine.http import PublicHttpClient


class FakeResponse:
    def __init__(self, body=b"{}", url="https://api.example.test/jobs", headers=None):
        self.body = body
        self.url = url
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def geturl(self):
        return self.url

    def read(self, n=-1):
        return self.body[:n] if n >= 0 else self.body


class SequenceOpener:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def open(self, req, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class HttpTests(unittest.TestCase):
    def test_json_success(self):
        opener = SequenceOpener([FakeResponse(json.dumps({"ok": True}).encode())])
        client = PublicHttpClient(opener=opener, sleep=lambda _: None)
        self.assertEqual(client.get_json("https://api.example.test/jobs", allowed_hosts={"api.example.test"}), {"ok": True})

    def test_429_retries(self):
        err = HTTPError("https://api.example.test/jobs", 429, "too many", {"Retry-After": "0"}, io.BytesIO())
        opener = SequenceOpener([err, FakeResponse(b"{}")])
        client = PublicHttpClient(opener=opener, sleep=lambda _: None)
        client.get_json("https://api.example.test/jobs", allowed_hosts={"api.example.test"})
        self.assertEqual(opener.calls, 2)

    def test_403_never_retries_or_bypasses(self):
        err = HTTPError("https://api.example.test/jobs", 403, "blocked", {}, io.BytesIO())
        opener = SequenceOpener([err])
        client = PublicHttpClient(opener=opener, sleep=lambda _: None)
        with self.assertRaises(VacancyEngineError) as ctx:
            client.get_json("https://api.example.test/jobs")
        self.assertEqual(ctx.exception.category, FailureCategory.BLOCKED)
        self.assertEqual(opener.calls, 1)

    def test_cross_host_redirect_rejected(self):
        opener = SequenceOpener([FakeResponse(b"{}", url="https://marketing.example.test/")])
        client = PublicHttpClient(opener=opener, sleep=lambda _: None)
        with self.assertRaises(VacancyEngineError) as ctx:
            client.get_json("https://api.example.test/jobs", allowed_hosts={"api.example.test"})
        self.assertEqual(ctx.exception.category, FailureCategory.UNEXPECTED_REDIRECT)


if __name__ == "__main__":
    unittest.main()
