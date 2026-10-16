import test from 'node:test';
import assert from 'node:assert/strict';
import {
  runStagedReview,STAGES,STAGE_CONTROL,STAGE_CURSOR,STAGE_RECEIPT
} from '../src/staged-review.mjs';

class FakeD1 {
  constructor(){this.meta=new Map([['seeded:greenhouse:automatticcareers','2026-10-16T10:29:03Z']]);this.writes=[];this.reads=[];}
  prepare(sql) {
    return {bind:(...args)=>({
      first:async()=>{
        this.reads.push(args[0]);
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
        if(sql.startsWith('DELETE FROM radar_metadata WHERE name GLOB ?')){
          const prefix=String(args[0]).slice(0,-1);
          let change=0;
          for(const key of [...this.meta.keys()]){
            if(key.startsWith(prefix)){this.meta.delete(key);this.writes.push(key);change++;}
          }
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
    ['v-old','submitted','','','','','https://job-boards.greenhouse.io/automatticcareers/jobs/old',''],
    ['v-applied','submitted','','','','','https://job-boards.greenhouse.io/automatticcareers/jobs/applied-no-d1','']
  ];
  if(opts.extraVacancies){
    for(let i=0;i<opts.extraVacancies;i++)vacancy.push([
      'v-extra-'+i,'seen','','','','',
      'https://job-boards.greenhouse.io/automatticcareers/jobs/extra-'+i,''
    ]);
  }
  if(opts.sparseGapAt!==undefined)vacancy.splice(opts.sparseGapAt,0,Array(8).fill(''));
  const apps=[['vacancy_id','','status','','application_url'],
    ['v-old','','submitted','','https://job-boards.greenhouse.io/automatticcareers/jobs/old'],
    ['v-applied','','submitted','','https://job-boards.greenhouse.io/automatticcareers/jobs/applied-no-d1']];
  const events=[['event_id','vacancy_id','','event_type','','status_after'],
    ['e-1','v-old','','submitted','','submitted'],
    ['e-2','v-applied','','submitted','','submitted']];
  const radar=[['observation_key','','','','','officiele_url','','','','','','','','sollicitatiehistorie','','','','actie'],
    ['greenhouse:automatticcareers:seen','','','','','https://job-boards.greenhouse.io/automatticcareers/jobs/seen']];
  const data={'Bronnen':source,'Vacatures':vacancy,'Applications':apps,'ApplicationEvents':events,'Nieuwe vacatures':radar};
  const m=/^'([^']+)'!([A-Z])(\d+):([A-Z])(\d+)?$/.exec(range);
  assert.ok(m,'Unexpected Google range '+range);
  const from=m[2].charCodeAt(0)-65,to=m[4].charCodeAt(0)-65,rows=data[m[1]];
  assert.ok(rows, 'Unexpected register sheet '+m[1]);
  const start=Number(m[3])-1,end=m[5]?Number(m[5]):rows.length;
  const values=rows.slice(start,end).map(r=>
    Array.from({length:to-from+1},(_,i)=>r[from+i]||''));
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
    {identity:'greenhouse:automatticcareers:applied-no-d1',source_id:'greenhouse',source_account:'automatticcareers',
      source_job_id:'applied-no-d1',title:'WordPress Developer',url:'https://job-boards.greenhouse.io/automatticcareers/jobs/applied-no-d1',source_url:'https://job-boards.greenhouse.io/automatticcareers/jobs/applied-no-d1',remote:'',location:''},
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
      if(opts.atsError)throw Error('Public API HTTP '+(opts.atsStatus||503));
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
test('first stage avoids redundant D1 control reread after atomic insert',async()=>{
  const h=harness();
  const out=await runStagedReview(h.env,h.ops);
  assert.equal(out.status,'ok');
  assert.equal(out.phase,'source_gate');
  assert.deepEqual(h.db.reads,[STAGE_CONTROL,STAGE_CURSOR],
    'an uncontended new cycle must use exactly the control and cursor reads');
  assert.equal(JSON.parse(h.db.meta.get(STAGE_CONTROL)).phase,1);
  assert.equal(h.db.writes.filter(key=>key===STAGE_CONTROL).length,3,
    'initial insert, atomic claim and checkpoint transition each remain guarded');
});

test('nine bounded Cron stages classify sources without writing business records',async()=>{
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
  assert.equal(result.rejected.applied,1,'a submitted application must be suppressed even if D1 has never seen the job');
  assert.equal(result.rejected.irrelevant,1);
  assert.equal(result.google_sheet_rows_written,0);
  assert.equal(result.application_submissions,0);
  assert.ok(h.db.writes.every(x=>x.startsWith('micro:v2:')));
  assert.ok(![...h.db.meta.keys()].some(x=>x.startsWith('micro:v2:snapshot:')));
  assert.equal(h.db.meta.get(STAGE_CURSOR),'1');
  assert.equal(JSON.parse(h.db.meta.get(STAGE_CONTROL)).status,'done');
  assert.equal(h.events.filter(x=>x.startsWith('ats:')).length,1);
});
test('paged vacancy history scans every source row in bounded 64-row sheets reads',async()=>{
  const h=harness({extraVacancies:130});
  h.ops.pagedVacancy=true;
  const original=h.ops.readRanges,reads=[];
  h.ops.readRanges=async(id,ranges,token)=>{
    reads.push(ranges);
    return original(id,ranges,token);
  };
  const phases=[];
  for(let i=0;i<30;i++){
    const outcome=await runStagedReview(h.env,h.ops);
    assert.ok(['ok','checkpointed'].includes(outcome.status),outcome.reason||'Unexpected state');
    phases.push(outcome.phase);
    if(outcome.phase==='review_only')break;
    h.advance(60000);
  }
  assert.equal(phases.at(-1),'review_only');
  assert.equal(phases.filter(x=>x==='vacancy_history').length,5,
    'one bounds call, three 64-row pages and one D1-only assembly');
  const history=reads.filter(x=>x.some(r=>r.startsWith("'Vacatures'!")));
  assert.equal(history.length,4);
  assert.ok(history[0].includes("'Vacatures'!A1:A"));
  for(const ranges of history.slice(1)){
    assert.equal(ranges.length,2);
    for(const range of ranges){
      const m=/[A-Z](\d+):[A-Z](\d+)$/.exec(range);
      assert.ok(m);
      assert.ok(Number(m[2])-Number(m[1])+1<=64);
    }
  }
  const receipt=JSON.parse(h.db.meta.get(STAGE_RECEIPT));
  assert.equal(receipt.status,'review_ready');
  assert.equal(receipt.application_submissions,0);
  assert.equal(receipt.google_sheet_rows_written,0);
  assert.equal(h.db.meta.get(STAGE_CURSOR),'1');
  assert.ok(![...h.db.meta.keys()].some(k=>k.startsWith('micro:v2:snapshot:')));
  assert.equal(h.events.filter(x=>x.startsWith('ats:')).length,1);
});
test('paged vacancy reconstruction retains blank gaps and later strong URLs',async()=>{
  const h=harness({extraVacancies:140,sparseGapAt:63});h.ops.pagedVacancy=true;
  assert.equal((await runStagedReview(h.env,h.ops)).phase,'source_gate');
  h.advance(60000);
  let history;
  for(let i=0;i<7;i++){
    const outcome=await runStagedReview(h.env,h.ops);
    if(outcome.status==='ok'){history=outcome;break;}
    assert.equal(outcome.status,'checkpointed');
    h.advance(60000);
  }
  assert.equal(history?.phase,'vacancy_history');
  const key=[...h.db.meta.keys()].find(x=>x.endsWith(':vacancy_history'));
  const rows=JSON.parse(h.db.meta.get(key)).data.rows;
  assert.equal(rows.length,144,'all original rows and deliberate gap are preserved');
  assert.ok(!rows[63]?.some(value=>Boolean(value)),'a blank page-boundary row is never elided');
  assert.ok(rows.some(row=>row[0]==='v-extra-139'),'later rows cannot be silently omitted');
  assert.equal(h.events.filter(e=>e.startsWith('ats:')).length,0);
});
test('paged scan fails closed instead of dropping history beyond safe capacity',async()=>{
  const h=harness({extraVacancies:1600});h.ops.pagedVacancy=true;
  assert.equal((await runStagedReview(h.env,h.ops)).phase,'source_gate');
  h.advance(60000);
  const fail=await runStagedReview(h.env,h.ops);
  assert.equal(fail.status,'partial');
  assert.equal(fail.reason,'Vacancy history size exceeds safe page limit');
  assert.match(h.db.meta.get(STAGE_CONTROL),/^failed:/);
  assert.equal(h.db.meta.has(STAGE_RECEIPT),false);
  assert.equal(h.events.some(x=>x.startsWith('ats:')),false);
});

test('paged vacancy scans fail closed when header differs before any ATS read',async()=>{
  const h=harness();h.ops.pagedVacancy=true;
  const orig=h.ops.readRanges;
  h.ops.readRanges=async(id,ranges,token)=>{
    const v=await orig(id,ranges,token);
    if(ranges.includes("'Vacatures'!A1:A"))v[0][0][0]='mismatch';
    return v;
  };
  assert.equal((await runStagedReview(h.env,h.ops)).phase,'source_gate');
  h.advance(60000);
  const bad=await runStagedReview(h.env,h.ops);
  assert.equal(bad.status,'partial');
  assert.equal(bad.reason,'Vacature Register header mismatch');
  assert.match(h.db.meta.get(STAGE_CONTROL),/^failed:/);
  assert.equal(h.events.some(x=>x.startsWith('ats:')),false);
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
  assert.equal((await runStagedReview(h.env,h.ops)).status,'halted');
});
test('transient ATS 503 retries once after one minute, then halts safely',async()=>{
  const h=harness({atsError:true});
  for(let i=0;i<STAGES.indexOf('official_ats');i++){
    await runStagedReview(h.env,h.ops);h.advance(60000);
  }
  const first=await runStagedReview(h.env,h.ops);
  assert.equal(first.status,'retry_scheduled');
  assert.equal(first.reason,'Public API HTTP 503');
  assert.equal(h.db.meta.has(STAGE_RECEIPT),false);
  const blocked=await runStagedReview(h.env,h.ops);
  assert.equal(blocked.status,'retry_wait');
  h.advance(60000);
  const second=await runStagedReview(h.env,h.ops);
  assert.equal(second.status,'partial');
  assert.equal(second.reason,'Public API HTTP 503');
  assert.match(h.db.meta.get(STAGE_CONTROL),/^failed:/);
  assert.equal((await runStagedReview(h.env,h.ops)).status,'halted');
  assert.equal(h.db.meta.has(STAGE_RECEIPT),false);
  assert.equal(h.events.filter(x=>x.startsWith('ats:')).length,2);
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

test('scheduled event requires BOTH explicit gates, not only RADAR_ENABLED',async()=>{
  const {default:worker}=await import('../src/index.mjs');
  let invoked=0;
  const ctx={waitUntil(){invoked++;}};
  await worker.scheduled({}, {RADAR_ENABLED:'1',RADAR_PIPELINE_MODE:'off'}, ctx);
  await worker.scheduled({}, {RADAR_ENABLED:'0',RADAR_PIPELINE_MODE:'staged_review'}, ctx);
  await worker.scheduled({}, {RADAR_ENABLED:'1'}, ctx);
  assert.equal(invoked,0);
});

test('each heavy history read is a separate checkpoint from building the policy index',async()=>{
  const h=harness();
  const phases=STAGES.slice(0,STAGES.indexOf('application_index'));
  for(let i=0;i<phases.length;i++){
    const outcome=await runStagedReview(h.env,h.ops);
    assert.equal(outcome.phase,phases[i]);
    h.advance(60000);
  }
  const keys=[...h.db.meta.keys()].filter(x=>x.startsWith('micro:v2:snapshot:'));
  assert.equal(keys.length,4,'Source, vacancy, application and events are separate checkpoints');
  assert.equal(keys.some(x=>x.endsWith(':application_index')),false);
  const app=JSON.parse(h.db.meta.get(keys.find(x=>x.endsWith(':application_rows'))));
  const evt=JSON.parse(h.db.meta.get(keys.find(x=>x.endsWith(':event_rows'))));
  assert.equal(app.data.rows[0][2],'status');
  assert.equal(evt.data.rows[0][5],'status_after');
  assert.equal(h.db.meta.has(STAGE_RECEIPT),false);
  const indexed=await runStagedReview(h.env,h.ops);
  assert.equal(indexed.phase,'application_index');
  assert.equal(h.events.filter(x=>x.startsWith('google-read')).length,4);
  assert.equal(h.db.meta.has(STAGE_RECEIPT),false);
});

test('candidate screen is provisional until a distinct final receipt stage succeeds',async()=>{
  const h=harness();
  const beforeFinal=STAGES.indexOf('review_only');
  for(let i=0;i<beforeFinal;i++){
    const outcome=await runStagedReview(h.env,h.ops);
    assert.equal(outcome.status,'ok');
    assert.equal(h.db.meta.has(STAGE_RECEIPT),false);
    h.advance(60000);
  }
  const key=[...h.db.meta.keys()].find(x=>x.endsWith(':candidate_screen'));
  assert.ok(key);
  const projected=JSON.parse(h.db.meta.get(key)).data;
  assert.equal(projected.review_count,1);
  assert.equal(projected.manual_review_required,true);
  assert.equal(projected.google_sheet_rows_written,0);
  assert.equal(projected.application_submissions,0);
  assert.equal((await runStagedReview(h.env,h.ops)).phase,'review_only');
  assert.equal(h.db.meta.has(STAGE_RECEIPT),true);
  assert.equal(h.db.meta.has(key),false,'private screening snapshot must be purged');
});

test('legacy v1 staged checkpoints cannot be resumed by the incompatible v2 pipeline',async()=>{
  const h=harness();
  const legacy='{"version":1,"run":"cycle_1792151163845_0","phase":4}';
  h.db.meta.set('micro:v1:control',legacy);
  h.db.meta.set('micro:v1:cursor','1');
  const result=await runStagedReview(h.env,h.ops);
  assert.equal(result.status,'ok');
  assert.equal(result.phase,'source_gate');
  assert.equal(h.db.meta.get('micro:v1:control'),legacy);
  assert.equal(h.db.meta.get('micro:v1:cursor'),'1');
  assert.equal(h.db.meta.has(STAGE_CURSOR),false);
  assert.equal(h.db.meta.has(STAGE_RECEIPT),false);
});

test('a running stage is never retried until its lease expires',async()=>{
  const h=harness();await runStagedReview(h.env,h.ops);
  h.advance(60000);
  const current=JSON.parse(h.db.meta.get(STAGE_CONTROL));
  h.db.meta.set(STAGE_CONTROL,'running:'+current.run+':1:'+(start+60000)+':0');
  assert.equal((await runStagedReview(h.env,h.ops)).status,'overlap_skipped');
  h.advance(119000);
  assert.equal((await runStagedReview(h.env,h.ops)).status,'overlap_skipped');
  assert.equal(h.events.filter(x=>x.startsWith('google-read')).length,1);
});

test('an interrupted phase is reclaimed exactly once without delivery',async()=>{
  const h=harness();await runStagedReview(h.env,h.ops);
  h.advance(60000);
  const current=JSON.parse(h.db.meta.get(STAGE_CONTROL));
  h.db.meta.set(STAGE_CONTROL,'running:'+current.run+':1:'+(start+60000)+':0');
  h.advance(120001);
  const first=await runStagedReview(h.env,h.ops);
  assert.equal(first.status,'recovered_retry');
  assert.equal(first.phase,'vacancy_history');
  assert.equal((await runStagedReview(h.env,h.ops)).phase,'vacancy_history');
  assert.equal(h.db.meta.has(STAGE_RECEIPT),false);
  assert.ok(h.db.writes.every(key=>key.startsWith('micro:v2:')));
});

test('a completed checkpoint is advanced instead of executed twice after crash',async()=>{
  const h=harness();await runStagedReview(h.env,h.ops);
  const next=JSON.parse(h.db.meta.get(STAGE_CONTROL));
  h.db.meta.set(STAGE_CONTROL,'running:'+next.run+':0:'+start+':0');
  h.advance(120001);
  const recovered=await runStagedReview(h.env,h.ops);
  assert.equal(recovered.status,'recovered_checkpoint');
  assert.equal(recovered.phase,'source_gate');
  assert.equal(JSON.parse(h.db.meta.get(STAGE_CONTROL)).phase,1);
  assert.equal(h.events.filter(x=>x.startsWith('google-read')).length,1);
  assert.equal((await runStagedReview(h.env,h.ops)).phase,'vacancy_history');
});

test('a second interrupted attempt halts with no unlimited replay',async()=>{
  const h=harness();await runStagedReview(h.env,h.ops);
  h.advance(60000);
  const current=JSON.parse(h.db.meta.get(STAGE_CONTROL));
  h.db.meta.set(STAGE_CONTROL,'running:'+current.run+':1:'+(start+60000)+':0');
  h.advance(120001);
  assert.equal((await runStagedReview(h.env,h.ops)).status,'recovered_retry');
  h.db.meta.set(STAGE_CONTROL,'running:'+current.run+':1:'+(start+180001)+':1');
  h.advance(120001);
  const halted=await runStagedReview(h.env,h.ops);
  assert.equal(halted.status,'partial');
  assert.equal(halted.reason,'interrupted_cycle');
  assert.match(h.db.meta.get(STAGE_CONTROL),/^failed:/);
  assert.equal((await runStagedReview(h.env,h.ops)).status,'halted');
  assert.equal(h.db.meta.has(STAGE_RECEIPT),false);
});

test('final receipt crash can be recovered without duplicate cursor or ATS poll',async()=>{
  const h=harness();
  for(let i=0;i<STAGES.length;i++){
    assert.equal((await runStagedReview(h.env,h.ops)).status,'ok');
    h.advance(60000);
  }
  const result=JSON.parse(h.db.meta.get(STAGE_RECEIPT));
  h.db.meta.set(STAGE_CURSOR,'0');
  h.db.meta.set(STAGE_CONTROL,'running:'+result.cycle+':8:'+(start+8*60000)+':0');
  h.advance(61000);
  const recovered=await runStagedReview(h.env,h.ops);
  assert.equal(recovered.status,'recovered_completed');
  assert.equal(h.db.meta.get(STAGE_CURSOR),'1');
  assert.equal(JSON.parse(h.db.meta.get(STAGE_CONTROL)).status,'done');
  assert.equal(h.events.filter(x=>x.startsWith('ats:')).length,1);
  assert.equal(JSON.parse(h.db.meta.get(STAGE_RECEIPT)).review_count,1);
});

test('legacy running claims remain fail-closed and do not restart',async()=>{
  const h=harness();await runStagedReview(h.env,h.ops);
  const current=JSON.parse(h.db.meta.get(STAGE_CONTROL));
  h.db.meta.set(STAGE_CONTROL,'running:'+current.run+':1');
  h.advance(60000);
  assert.equal((await runStagedReview(h.env,h.ops)).status,'overlap_skipped');
  assert.equal(h.events.filter(x=>x.startsWith('google-read')).length,1);
});

test('invalid attempt counters cannot bypass the bounded retry limit',async()=>{
  const h=harness();await runStagedReview(h.env,h.ops);
  const c=JSON.parse(h.db.meta.get(STAGE_CONTROL));
  h.db.meta.set(STAGE_CONTROL,JSON.stringify({...c,attempts:99}));
  const answer=await runStagedReview(h.env,h.ops);
  assert.equal(answer.status,'partial');
  assert.equal(answer.reason,'invalid_control');
  assert.equal(h.events.filter(x=>x.startsWith('google-read')).length,1);
});

test('HTTP 429 is fail-closed, without automatic replays or application writes',async()=>{
  const h=harness({atsError:true,atsStatus:429});
  for(let i=0;i<STAGES.indexOf('official_ats');i++){
    await runStagedReview(h.env,h.ops);h.advance(60000);
  }
  const failed=await runStagedReview(h.env,h.ops);
  assert.equal(failed.status,'partial');
  assert.equal(failed.reason,'Public API HTTP 429');
  assert.match(h.db.meta.get(STAGE_CONTROL),/^failed:/);
  assert.equal((await runStagedReview(h.env,h.ops)).status,'halted');
  assert.equal(h.events.filter(x=>x.startsWith('ats:')).length,1);
  assert.equal(h.db.meta.has(STAGE_RECEIPT),false);
});

test('the 12-minute expiry takes precedence over a stale retry deadline',async()=>{
  const h=harness();await runStagedReview(h.env,h.ops);
  const state=JSON.parse(h.db.meta.get(STAGE_CONTROL));
  h.db.meta.set(STAGE_CONTROL,JSON.stringify({
    ...state,attempts:1,retry_after:start+50*60000,
    expires_at:new Date(start+60000).toISOString()
  }));
  h.advance(120000);
  const result=await runStagedReview(h.env,h.ops);
  assert.equal(result.status,'partial');
  assert.equal(result.reason,'expired_cycle');
  assert.match(h.db.meta.get(STAGE_CONTROL),/^failed:/);
  assert.equal(h.db.meta.has(STAGE_RECEIPT),false);
});
