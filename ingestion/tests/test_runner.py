import tempfile, unittest
from pathlib import Path
from vacature_ingestion.http import FetchError
from vacature_ingestion.models import SourceSpec
from vacature_ingestion.runner import IngestionRunner

class FakeClient:
    def __init__(self,values): self.values=list(values); self.calls=0
    def get_json(self,url,headers=None):
        self.calls+=1; value=self.values.pop(0)
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

if __name__ == "__main__": unittest.main()
