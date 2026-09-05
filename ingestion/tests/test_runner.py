import tempfile, unittest
from pathlib import Path
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
    def test_himalayas_offset_pagination(self):
        spec=SourceSpec("himalayas","discovery_api","himalayas","global",max_jobs=2)
        p1={"jobs":[{"guid":"1","title":"A","applicationLink":"https://himalayas.app/jobs/1"}],"totalCount":2}
        p2={"jobs":[{"guid":"2","title":"B","applicationLink":"https://himalayas.app/jobs/2"}],"totalCount":2}
        c=FakeClient([p1,p2]); r=self.runner.run_source(spec,client=c)
        self.assertEqual((r.fetched,c.calls),(2,2))
        self.assertIn("offset=0",c.urls[0]); self.assertIn("offset=1",c.urls[1])
        self.assertNotIn("cursor=",c.urls[0]+c.urls[1])

if __name__ == "__main__": unittest.main()
