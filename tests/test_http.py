import io
import unittest
from email.message import Message
from urllib.error import HTTPError

from vacature_engine.errors import FailureCategory, VacancyEngineError
from vacature_engine.http import PublicHttpClient, validate_public_url


class FakeResponse:
    def __init__(self, body=b"{}", url="https://api.example.com/data", headers=None):
        self.body = body
        self.url = url
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, amount=-1):
        return self.body if amount < 0 else self.body[:amount]


class ScriptedOpener:
    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = []

    def open(self, req, timeout=None):
        self.calls.append(req.full_url)
        if not self.actions:
            raise AssertionError("unexpected extra network call")
        action = self.actions.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action


def http_error(url, code, **headers):
    message = Message()
    for key, value in headers.items():
        message[key.replace("_", "-")] = str(value)
    return HTTPError(url, code, "err", message, io.BytesIO())


class HttpTests(unittest.TestCase):
    def test_json_success(self):
        opener = ScriptedOpener([FakeResponse(b'{"ok":true}')])
        result = PublicHttpClient(opener=opener).get_json(
            "https://api.example.com/data", allowed_hosts={"api.example.com"}
        )
        self.assertEqual(result, {"ok": True})

    def test_initial_host_mismatch_rejected_before_network(self):
        opener = ScriptedOpener([])
        with self.assertRaises(VacancyEngineError):
            PublicHttpClient(opener=opener).get_bytes(
                "https://evil.example/data", allowed_hosts={"api.example.com"}
            )
        self.assertFalse(opener.calls)

    def test_private_and_local_targets_rejected(self):
        for url in (
            "http://127.0.0.1/",
            "http://10.0.0.1/",
            "http://169.254.169.254/",
            "http://localhost/",
            "http://service.internal/",
            "http://intranet/",
        ):
            with self.subTest(url=url), self.assertRaises(VacancyEngineError):
                validate_public_url(url)

    def test_nonstandard_port_rejected(self):
        with self.assertRaises(VacancyEngineError):
            validate_public_url("https://example.com:8443/jobs")

    def test_url_credentials_rejected(self):
        with self.assertRaises(VacancyEngineError):
            validate_public_url("https://user:pass@example.com/jobs")

    def test_same_host_redirect_allowed(self):
        opener = ScriptedOpener(
            [
                http_error("https://api.example.com/a", 302, Location="/b"),
                FakeResponse(b"ok", url="https://api.example.com/b"),
            ]
        )
        body = PublicHttpClient(opener=opener).get_bytes(
            "https://api.example.com/a", allowed_hosts={"api.example.com"}
        )
        self.assertEqual(body, b"ok")
        self.assertEqual(opener.calls, ["https://api.example.com/a", "https://api.example.com/b"])

    def test_cross_host_redirect_rejected_before_follow(self):
        opener = ScriptedOpener(
            [http_error("https://api.example.com/a", 302, Location="https://evil.example/b")]
        )
        with self.assertRaises(VacancyEngineError) as ctx:
            PublicHttpClient(opener=opener).get_bytes(
                "https://api.example.com/a", allowed_hosts={"api.example.com"}
            )
        self.assertEqual(ctx.exception.category, FailureCategory.UNEXPECTED_REDIRECT)
        self.assertEqual(opener.calls, ["https://api.example.com/a"])

    def test_redirect_without_location_rejected(self):
        opener = ScriptedOpener([http_error("https://api.example.com/a", 302)])
        with self.assertRaises(VacancyEngineError) as ctx:
            PublicHttpClient(opener=opener).get_bytes(
                "https://api.example.com/a", allowed_hosts={"api.example.com"}
            )
        self.assertEqual(ctx.exception.category, FailureCategory.MALFORMED)

    def test_403_never_retries_or_bypasses(self):
        opener = ScriptedOpener([http_error("https://api.example.com/a", 403)])
        with self.assertRaises(VacancyEngineError) as ctx:
            PublicHttpClient(opener=opener, sleep=lambda _: None).get_bytes(
                "https://api.example.com/a", allowed_hosts={"api.example.com"}
            )
        self.assertEqual(ctx.exception.category, FailureCategory.BLOCKED)
        self.assertEqual(len(opener.calls), 1)

    def test_429_retries(self):
        sleeps = []
        opener = ScriptedOpener(
            [
                http_error("https://api.example.com/a", 429, Retry_After="2"),
                FakeResponse(b"ok"),
            ]
        )
        body = PublicHttpClient(opener=opener, sleep=sleeps.append).get_bytes(
            "https://api.example.com/a", allowed_hosts={"api.example.com"}
        )
        self.assertEqual(body, b"ok")
        self.assertEqual(sleeps, [2.0])

    def test_max_bytes_content_length_and_stream(self):
        for response in (
            FakeResponse(b"x", headers={"Content-Length": "11"}),
            FakeResponse(b"01234567890"),
        ):
            opener = ScriptedOpener([response])
            with self.subTest(headers=response.headers), self.assertRaises(VacancyEngineError):
                PublicHttpClient(opener=opener, max_bytes=10).get_bytes(
                    "https://api.example.com/a", allowed_hosts={"api.example.com"}
                )

    def test_invalid_json_rejected(self):
        opener = ScriptedOpener([FakeResponse(b"not-json")])
        with self.assertRaises(VacancyEngineError):
            PublicHttpClient(opener=opener).get_json(
                "https://api.example.com/a", allowed_hosts={"api.example.com"}
            )

    def test_invalid_client_configuration_rejected(self):
        bad = [
            {"attempts": 0},
            {"attempts": True},
            {"timeout": 0},
            {"timeout": float("nan")},
            {"max_bytes": 0},
            {"max_redirects": -1},
            {"max_redirects": True},
        ]
        for kwargs in bad:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PublicHttpClient(**kwargs)

    def test_https_downgrade_redirect_rejected(self):
        opener = ScriptedOpener([http_error("https://api.example.com/a", 302, Location="http://api.example.com/b")])
        with self.assertRaises(VacancyEngineError) as ctx:
            PublicHttpClient(opener=opener).get_bytes(
                "https://api.example.com/a", allowed_hosts={"api.example.com"}
            )
        self.assertEqual(ctx.exception.category, FailureCategory.UNEXPECTED_REDIRECT)
        self.assertEqual(len(opener.calls), 1)

    def test_retry_policy_allows_at_most_one_retry(self):
        with self.assertRaises(ValueError):
            PublicHttpClient(attempts=3)
        client = PublicHttpClient(attempts=2, opener=ScriptedOpener([http_error("https://api.example.com/a", 500), http_error("https://api.example.com/a", 500)]), sleep=lambda _: None)
        with self.assertRaises(VacancyEngineError):
            client.get_bytes("https://api.example.com/a", allowed_hosts={"api.example.com"})
        self.assertEqual(len(client.opener.calls), 2)


if __name__ == "__main__":
    unittest.main()
