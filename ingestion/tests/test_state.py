import tempfile, unittest
from pathlib import Path
from vacature_ingestion.models import SourceSpec
from vacature_ingestion.runner import IngestionRunner

def gh(i,title="Developer",url=None): return {"id":i,"title":title,"content":"Body","absolute_url":url or f"https://example.com/jobs/{i}"}

class StateTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory(); self.r=IngestionRunner(Path(self.td.name)/"s.db"); self.spec=SourceSpec("greenhouse","ats","greenhouse","acme","Acme")
    def tearDown(self): self.r.close(); self.td.cleanup()
    def test_new_unchanged_updated(self):
        a=self.r.ingest_records(self.spec,[gh(1)]); b=self.r.ingest_records(self.spec,[gh(1)]); c=self.r.ingest_records(self.spec,[gh(1,"Senior")]); self.assertEqual((a.new,b.unchanged,c.updated),(1,1,1))
    def test_job_id_survives_url_change(self):
        self.r.ingest_records(self.spec,[gh(1,url="https://old.example/1")]); self.r.ingest_records(self.spec,[gh(1,url="https://new.example/1")]); self.assertEqual(len(self.r.state.list_jobs()),1)
    def test_weak_fingerprint_does_not_merge(self):
        x=self.r.ingest_records(self.spec,[gh(1,url="https://a.example/1"),gh(2,url="https://b.example/2")]); self.assertEqual(x.new,2)
    def test_tracking_variations_merge(self):
        x=self.r.ingest_records(self.spec,[gh(1,url="https://example.com/1?utm_source=a"),gh(1,url="https://example.com/1?utm_source=b")]); self.assertEqual((x.new,x.duplicate_observations),(1,1))
    def test_two_missing_snapshots_close(self):
        self.r.ingest_records(self.spec,[gh(1)]); self.assertEqual(self.r.ingest_records(self.spec,[]).closed,0); self.assertEqual(self.r.ingest_records(self.spec,[]).closed,1)
    def test_other_source_blocks_false_close(self):
        other=SourceSpec("other","ats","greenhouse","other","Acme"); url="https://example.com/shared"
        self.r.ingest_records(self.spec,[gh(1,url=url)]); self.r.ingest_records(other,[gh(9,url=url)]); self.r.ingest_records(self.spec,[]); self.assertEqual(self.r.ingest_records(self.spec,[]).closed,0); self.assertEqual(self.r.state.list_jobs()[0]["status"],"active")
    def test_threshold_three(self):
        spec=SourceSpec("greenhouse","ats","greenhouse","three",missing_close_threshold=3); self.r.ingest_records(spec,[gh(7)]); self.assertEqual(self.r.ingest_records(spec,[]).closed,0); self.assertEqual(self.r.ingest_records(spec,[]).closed,0); self.assertEqual(self.r.ingest_records(spec,[]).closed,1)
    def test_partial_never_advances_missing(self):
        self.r.ingest_records(self.spec,[gh(1)]); x=self.r.ingest_records(self.spec,[],complete_snapshot=False); self.assertEqual((x.missing,x.closed),(0,0))
    def test_health_keeps_last_success_count(self):
        self.r.ingest_records(self.spec,[gh(1)]); rid=self.r.state.start_run(self.spec.instance_id,"2026-09-05T00:00:00+00:00"); self.r.state.finish_run(rid,success=False,fetched=0,normalized=0,failure_category="timeout",failure_message="x"); h=self.r.state.source_health(self.spec.instance_id); self.assertEqual(h["last_result_count"],1)

if __name__ == "__main__": unittest.main()
