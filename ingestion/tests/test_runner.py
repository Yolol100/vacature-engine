import tempfile, unittest
import threading
from pathlib import Path
from unittest.mock import patch
from vacature_ingestion.http import FetchError
from vacature_ingestion.models import SourceSpec
from vacature_ingestion.runner import IngestionRunner

class FakeClient:
    def __init__(self,values): self.values=list(values); self.calls=0; self.urls=[]
    def get_json(self,url,headers=None):
        self.calls+=1; self.urls.append(url); value=self.values.pop(0)
        if isinstance(value,Exception): raise value
        return value

class RunnerTests(unittest.TestCase):
    def setUp(self): self.td=tempfile.TemporaryDirectory(); self.runner=IngestionRunner(Path(self.td.name)/"s.db")
    def tearDown(self): self.runner.close(); self.td.cleanup()
    def test_three_provider_fetches_overlap_but_sqlite_writes_remain_ordered(self):
        barrier = threading.Barrier(3)
        workers = set()
        lock = threading.Lock()
        class ParallelClient:
            def __init__(self, **kwargs):
                pass
            def get_json(self, url, headers=None):
                with lock:
                    workers.add(threading.get_ident())
                barrier.wait(timeout=4)
                account = url.split("/boards/", 1)[1].split("/", 1)[0]
                return {"jobs": [{
                    "id": account,
                    "title": "WordPress Developer",
                    "absolute_url": "https://example.org/job/" + account,
                }]}
        specs = [
            SourceSpec("greenhouse", "ats", "greenhouse", f"employer{i}")
            for i in range(3)
        ]
        with patch("vacature_ingestion.runner.HttpClient", ParallelClient):
            rows = self.runner.run_many_parallel(specs, max_workers=3)
        self.assertEqual(len(workers), 3)
        self.assertEqual([r.source_instance for r in rows],
                         [s.instance_id for s in specs])
        self.assertTrue(all(r.success and r.fetched == 1 for r in rows))
        self.assertEqual(len(self.runner.state.list_jobs()), 3)
        self.assertTrue(all(r.started_at for r in rows))

    def test_parallel_fetch_failure_is_recorded_once_without_retry(self):
        calls = []
        lock = threading.Lock()
        class FailOneClient:
            def __init__(self, **kwargs):
                pass
            def get_json(self, url, headers=None):
                with lock:
                    calls.append(url)
                if "/fail/" in url:
                    raise FetchError("timeout_or_network", "temporary outage")
                return {"jobs": [{"id": "ok", "title": "WordPress Developer",
                                  "absolute_url": "https://example.org/job/ok"}]}
        specs = [
            SourceSpec("greenhouse", "ats", "greenhouse", "fail"),
            SourceSpec("greenhouse", "ats", "greenhouse", "ok"),
        ]
        with patch("vacature_ingestion.runner.HttpClient", FailOneClient):
            results = self.runner.run_many_parallel(specs, max_workers=2)
        self.assertEqual(len(calls), 2)
        self.assertEqual([r.success for r in results], [False, True])
        self.assertEqual(results[0].failure_category, "timeout_or_network")
        self.assertEqual((results[0].missing, results[0].closed), (0, 0))
        self.assertEqual(len(self.runner.state.list_jobs()), 1)

    def test_parallel_fetch_budgets_are_strict(self):
        spec = SourceSpec("greenhouse", "ats", "greenhouse", "company")
        with self.assertRaises(ValueError):
            self.runner.run_many_parallel([spec] * 2)
        with self.assertRaises(ValueError):
            self.runner.run_many_parallel([spec], max_workers=4)
        with self.assertRaises(ValueError):
            self.runner.run_many_parallel([spec] * 9, max_workers=1)

    def test_failure_isolated(self):
        spec=SourceSpec("greenhouse","ats","greenhouse","acme")
        self.runner.run_source(spec,client=FakeClient([{"jobs":[{"id":1,"title":"Dev","absolute_url":"https://example.com/1"}]}]))
        result=self.runner.run_source(spec,client=FakeClient([FetchError("timeout_or_network","boom")]))
        self.assertFalse(result.success); self.assertEqual(self.runner.state.list_jobs()[0]["status"],"active")
    def test_lever_pagination(self):
        spec=SourceSpec("lever","ats","lever","acme",max_jobs=3,options={"page_size":2})
        p1=[{"id":"a","text":"A","hostedUrl":"https://jobs.lever.co/a"},{"id":"b","text":"B","hostedUrl":"https://jobs.lever.co/b"}]; p2=[{"id":"c","text":"C","hostedUrl":"https://jobs.lever.co/c"}]
        c=FakeClient([p1,p2]); r=self.runner.run_source(spec,client=c); self.assertEqual((r.fetched,c.calls),(3,2))
    def test_corrupt_shape_isolated(self):
        spec=SourceSpec("greenhouse","ats","greenhouse","bad"); r=self.runner.run_source(spec,client=FakeClient([{"jobs":"bad"}]))
        self.assertFalse(r.success)
    def test_review_queue_only_new_or_updated(self):
        spec=SourceSpec("greenhouse","ats","greenhouse","acme")
        first={"id":1,"title":"Dev","absolute_url":"https://example.com/1","content":"A"}
        r1=self.runner.run_source(spec,client=FakeClient([{"jobs":[first]}]))
        self.assertEqual([x["ingestion_change"] for x in r1.review_observations],["new"])
        r2=self.runner.run_source(spec,client=FakeClient([{"jobs":[first]}]))
        self.assertEqual(r2.review_observations,[])
        changed={**first,"content":"B"}
        r3=self.runner.run_source(spec,client=FakeClient([{"jobs":[changed]}]))
        self.assertEqual([x["ingestion_change"] for x in r3.review_observations],["updated"])
    def test_himalayas_filtered_search_pages(self):
        spec=SourceSpec("himalayas","discovery_api","himalayas","global",max_jobs=2,options={"query":"wordpress","sort":"recent"})
        p1={"jobs":[{"guid":"1","title":"A","applicationLink":"https://himalayas.app/jobs/1"}]}
        p2={"jobs":[{"guid":"2","title":"B","applicationLink":"https://himalayas.app/jobs/2"}]}
        c=FakeClient([p1,p2]); r=self.runner.run_source(spec,client=c)
        self.assertEqual((r.fetched,c.calls),(2,2))
        self.assertIn("/search?",c.urls[0]); self.assertIn("q=wordpress",c.urls[0]); self.assertIn("page=1",c.urls[0]); self.assertIn("page=2",c.urls[1])
    def test_himalayas_browse_uses_cursor(self):
        spec=SourceSpec("himalayas","discovery_api","himalayas","global",max_jobs=2)
        p1={"jobs":[{"guid":"1","title":"A","applicationLink":"https://himalayas.app/jobs/1"}],"nextCursor":"opaque"}
        p2={"jobs":[{"guid":"2","title":"B","applicationLink":"https://himalayas.app/jobs/2"}]}
        c=FakeClient([p1,p2]); r=self.runner.run_source(spec,client=c)
        self.assertEqual((r.fetched,c.calls),(2,2)); self.assertIn("cursor=opaque",c.urls[1]); self.assertNotIn("offset=",c.urls[0]+c.urls[1])


    def test_missing_job_collection_is_not_a_successful_empty_source(self):
        for provider in ("ashby", "greenhouse", "smartrecruiters", "workable"):
            with self.subTest(provider=provider):
                spec = SourceSpec(provider, "ats", provider, "acme")
                response = {"error": "Unexpected provider schema"}
                result = self.runner.run_source(spec, client=FakeClient([response]))
                self.assertFalse(result.success)
                self.assertEqual(result.failure_category, "parsing_or_adapter_failure")
                self.assertEqual((result.missing, result.closed), (0, 0))

    def test_malformed_greenhouse_response_cannot_close_known_role(self):
        spec = SourceSpec("greenhouse", "ats", "greenhouse", "acme")
        original = {"id": 42, "title": "WordPress Engineer",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/42"}
        first = self.runner.run_source(spec, client=FakeClient([{"jobs": [original]}]))
        self.assertTrue(first.success)
        self.assertEqual(first.new, 1)
        for _ in range(2):
            failed = self.runner.run_source(spec, client=FakeClient([{}]))
            self.assertFalse(failed.success)
            self.assertEqual((failed.missing, failed.closed), (0, 0))
        self.assertEqual(self.runner.state.list_jobs()[0]["status"], "active")

if __name__ == "__main__": unittest.main()
