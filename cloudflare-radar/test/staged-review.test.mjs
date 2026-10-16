import test from 'node:test';
import assert from 'node:assert/strict';
import {
  runStagedReview,STAGES,STAGE_CONTROL,STAGE_CURSOR,STAGE_RECEIPT
} from '../src/staged-review.mjs';

class FakeD1 {
  constructor(){this.meta=new Map([['seeded:greenhouse:automatticcareers','2026-10-16T10:29:03Z']]);this.writes=[];}
  prepare(sql) {
    return {bind:(...args)=>({
      first:async()=>{
        if(sql.startsWith('SELECT value FROM radar_metadata'))
          return this.meta.has(args[0])?{value:this.meta.get(args[0])}:null;
        throw Error('Unexpected D1 first: '+sql);
      },
      run:async()=>{
        if(sql.startsWith('INSERT OR IGNORE INTO radar_metadata')){
          const change=Number(!this.meta.has(args[0]));
          if(change){this.meta.set(args[0],args[1]);this.writes.push(args[0]);}
          return {meta:{changes:change}};
        }
        if(sql.startsWith('INSERT INTO radar_metadata(name,value)')){
          this.meta.set(args[0],args[1]);this.writes.push(args[0]);
          return {meta:{changes:1}};
        }
        if(sql.startsWith('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')){
          const change=Number(this.meta.get(args[1])===args[2]);
          if(change){this.meta.set(args[1],args[0]);this.writes.push(args[1]);}
          return {meta:{changes:change}};
        }
        if(sql.startsWith('DELETE FROM radar_metadata WHERE name=?')){
          this.meta.delete(args[0]);this.writes.push(args[0]);
          return {meta:{changes:1}};
        }
        throw Error('Unexpected D1 mutation: '+sql);
      }
    })};
  }
}
const start=Date.parse('2026-10-16T13:00:00Z');
function testEnv(db){return {
  RADAR_ENABLED:'1',RADAR_PIPELINE_MODE:'staged_review',
  RADAR_DB:db,GOOGLE_SERVICE_ACCOUNT_JSON:'fake-only-not-real',
  VACATURE_REGISTER_ID:'register-test',RADAR_RESULT_ID:'radar-test'
};}
function rangeValues(range,opts) {
  const source=[
    ['source_id','status'],
    ['greenhouse','active'],
    ['company-automattic','active'],
    ['lever','active'],
    ['company-kinsta','active'],
    ['ashby','active'],
    ['company-zapier','active']
  ].map(([id,status])=>{
    const row=Array(13).fill('');
    row[0]=id;row[12]=status;return row;
  });
  const vacancy=[
    ['vacancy_id','status','','','','','canonical_url','official_url'],
    ['v-old','submitted','','','','','https://job-boards.greenhouse.io/automatticcareers/jobs/old','']
  ];
  const apps=[['vacancy_id','','status','','application_url'],
    ['v-old','','submitted','','https://job-boards.greenhouse.io/automatticcareers/jobs/old']];
  const events=[['event_id','vacancy_id','','event_type','','status_after'],
    ['e-1','v-old','','submitted','','submitted']];
  const radar=[['observation_key','','','','','officiele_url','','','','','','','','sollicitatiehistorie','','','','actie'],
    ['greenhouse:automatticcareers:seen','','','','','https://job-boards.greenhouse.io/automatticcareers/jobs/seen']];
  const data={'Bronnen':source,'Vacatures':vacancy,'Applications':apps,'ApplicationEvents':events,'Nieuwe vacatures':radar};
  const m=/^'([^']+)'!([A-Z])1:([A-Z])$/.exec(range);
  assert.ok(m,'Unexpected Google range '+range);
  const from=m[2].charCodeAt(0)-65,to=m[3].charCodeAt(0)-65,rows=data[m[1]];
  assert.ok(rows, 'Unexpected register sheet '+m[1]);
  const values=rows.map(r=>Array.from({length:to-from+1},(_,i)=>r[from+i]||''));
  if(opts.breakHeader&&m[1]==='Applications'&&m[2]==='C')values[0][0]='BROKEN';
  if(opts.blockEmployer&&m[1]==='Bronnen'&&m[2]==='M')values[2][0]='blocked';
  return values;
}
function harness(opts={}){
  const db=new FakeD1(),events=[],env=testEnv(db);
  let clock=start;
  const jobs=[
    {identity:'greenhouse:automatticcareers:old',source_id:'greenhouse',source_account:'automatticcareers',
      source_job_id:'old',title:'WordPress Developer',url:'https://job-boards.greenhouse.io/automatticcareers/jobs/old',source_url:'https://job-boards.greenhouse.io/automatticcareers/jobs/old',remote:'',location:''},
    {identity:'greenhouse:automatticcareers:new',source_id:'greenhouse',source_account:'automatticcareers',
      source_job_id:'new',title:'WordPress Developer',url:'https://job-boards.greenhouse.io/automatticcareers/jobs/new',source_url:'https://job-boards.greenhouse.io/automatticcareers/jobs/new',remote:'',location:''},
    {identity:'greenhouse:automatticcareers:seen',source_id:'greenhouse',source_account:'automatticcareers',
      source_job_id:'seen',title:'WordPress Developer',url:'https://job-boards.greenhouse.io/automatticcareers/jobs/seen',source_url:'https://job-boards.greenhouse.io/automatticcareers/jobs/seen',remote:'',location:''},
    {identity:'greenhouse:automatticcareers:irrelevant',source_id:'greenhouse',source_account:'automatticcareers',
      source_job_id:'irrelevant',title:'Human Resources Specialist',url:'https://job-boards.greenhouse.io/automatticcareers/jobs/irrelevant',source_url:'https://job-boards.greenhouse.io/automatticcareers/jobs/irrelevant',remote:'',location:''}
  ];
  const ops={
    now:()=>clock,
    accessToken:async()=>{events.push('google-auth');return 'mock-token';},
    readRanges:async(id,ranges,token)=>{
      assert.equal(token,'mock-token');events.push('google-read:'+id);
      return ranges.map(range=>rangeValues(range,opts));
    },
    publicJobs:async source=>{
      events.push('ats:'+source.source_id+':'+source.account);
      if(opts.atsError)throw Error('Public API HTTP 503');
      return jobs;
    },
    existingKeys:async(db,jobs)=>{events.push('d1-existing');return new Set(['greenhouse:automatticcareers:old']);}
  };
  return {db,env,ops,events,advance:ms=>clock+=ms};
}
test('disabled defaults: no DB access, Google reads, ATS calls or submission',async()=>{
  const h=harness();
  assert.equal((await runStagedReview({...h.env,RADAR_ENABLED:'0'},h.ops)).status,'disabled');
  assert.equal((await runStagedReview({...h.env,RADAR_PIPELINE_MODE:'off'},h.ops)).status,'disabled');
  assert.equal(h.events.length,0);
  assert.equal(h.db.writes.length,0);
});
test('six small Cron stages classify sources without writing business records',async()=>{
  const h=harness(),phases=[];
  for(let i=0;i<STAGES.length;i++){
    const result=await runStagedReview(h.env,h.ops);
    assert.equal(result.status,'ok',result.reason||'');
    assert.equal(result.phase,STAGES[i]);
    assert.equal(result.phase_index,i+1);
    assert.equal(result.new_records,0);
    phases.push(result.phase);
    h.advance(60000);
  }
  assert.deepEqual(phases,STAGES);
  const result=JSON.parse(h.db.meta.get(STAGE_RECEIPT));
  assert.equal(result.status,'review_ready');
  assert.equal(result.source,'greenhouse:automatticcareers');
  assert.equal(result.review_count,1);
  assert.equal(result.candidates[0].identity,'greenhouse:automatticcareers:new');
  assert.equal(result.rejected.radar_duplicates,1);
  assert.equal(result.rejected.irrelevant,1);
  assert.equal(result.google_sheet_rows_written,0);
  assert.equal(result.application_submissions,0);
  assert.ok(h.db.writes.every(x=>x.startsWith('micro:v1:')));
  assert.ok(![...h.db.meta.keys()].some(x=>x.startsWith('micro:v1:snapshot:')));
  assert.equal(h.db.meta.get(STAGE_CURSOR),'1');
  assert.equal(JSON.parse(h.db.meta.get(STAGE_CONTROL)).status,'done');
  assert.equal(h.events.filter(x=>x.startsWith('ats:')).length,1);
});
test('an inactive employer blocks the source before any ATS access',async()=>{
  const h=harness({blockEmployer:true});
  const r=await runStagedReview(h.env,h.ops);
  // Source gate may select the next active employer instead; never select blocked Greenhouse.
  assert.equal(r.status,'ok');
  const source=JSON.parse(h.db.meta.get([...h.db.meta.keys()].find(x=>x.endsWith(':source_gate'))));
  assert.notEqual(source.data.source,'greenhouse:automatticcareers');
});
test('missing header stops the cycle fail-closed; no ATS, no Sheets writes',async()=>{
  const h=harness({breakHeader:true});
  await runStagedReview(h.env,h.ops);
  h.advance(60000);await runStagedReview(h.env,h.ops);
  h.advance(60000);const failed=await runStagedReview(h.env,h.ops);
  assert.equal(failed.status,'partial');
  assert.equal(failed.reason,'Application header mismatch');
  assert.match(h.db.meta.get(STAGE_CONTROL),/^failed:/);
  assert.equal(h.events.filter(x=>x.startsWith('ats:')).length,0);
  assert.equal((await runStagedReview(h.env,h.ops)).status,'partial');
});
test('ATS failure leaves the pipeline failed, without false candidate output',async()=>{
  const h=harness({atsError:true});
  for(let i=0;i<4;i++){await runStagedReview(h.env,h.ops);h.advance(60000);}
  const failed=await runStagedReview(h.env,h.ops);
  assert.equal(failed.status,'partial');
  assert.equal(failed.reason,'Public API HTTP 503');
  assert.equal(h.db.meta.has(STAGE_RECEIPT),false);
  assert.equal(h.events.filter(x=>x.startsWith('ats:')).length,1);
});
test('expires after twelve minutes without automatic restart or delivery',async()=>{
  const h=harness();await runStagedReview(h.env,h.ops);
  h.advance(13*60000);
  const o=await runStagedReview(h.env,h.ops);
  assert.equal(o.status,'partial');
  assert.equal(o.reason,'expired_cycle');
  assert.equal(h.events.filter(x=>x.startsWith('ats:')).length,0);
  assert.equal(h.db.meta.has(STAGE_RECEIPT),false);
});
test('repeated overlapping invocations cannot fetch source twice',async()=>{
  const h=harness();
  const outcomes=await Promise.all([runStagedReview(h.env,h.ops),runStagedReview(h.env,h.ops)]);
  assert.equal(outcomes.filter(x=>x.status==='ok').length,1);
  assert.equal(outcomes.filter(x=>x.status==='overlap_skipped').length,1);
});
