import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from vacature_ingestion.http import FetchError, HttpClient

class FakeResponse:
    def __init__(self,body,status=200,headers=None): self.body=body; self.status=status; self.headers=headers or {}
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,amount): return self.body[:amount]

class HttpTests(unittest.TestCase):
    @patch("vacature_ingestion.http.time.sleep",return_value=None)
    @patch("vacature_ingestion.http.urlopen")
    def test_rate_limit_retry(self,mocked,_sleep):
        mocked.side_effect=[HTTPError("https://x",429,"rate",{},io.BytesIO(b"")),FakeResponse(b'{"ok":true}')]
        self.assertEqual(HttpClient(retries=1).get_json("https://x"),{"ok":True})
    @patch("vacature_ingestion.http.time.sleep",return_value=None)
    @patch("vacature_ingestion.http.urlopen")
    def test_network_bounded_retry(self,mocked,_sleep):
        mocked.side_effect=URLError("timeout")
        with self.assertRaises(FetchError): HttpClient(retries=1).get_json("https://x")
        self.assertEqual(mocked.call_count,2)
    @patch("vacature_ingestion.http.urlopen",return_value=FakeResponse(b"bad"))
    def test_bad_json_closed(self,_):
        with self.assertRaises(FetchError): HttpClient(retries=0).get_json("https://x")
    @patch("vacature_ingestion.http.urlopen",return_value=FakeResponse(b"123456",headers={"Content-Length":"6"}))
    def test_size_bound(self,_):
        with self.assertRaises(FetchError): HttpClient(retries=0,max_response_bytes=5).get_json("https://x")
    @patch("vacature_ingestion.http.urlopen",return_value=FakeResponse("héllo".encode()))
    def test_text(self,_): self.assertEqual(HttpClient(retries=0).get_text("https://x"),"héllo")

if __name__ == "__main__": unittest.main()
