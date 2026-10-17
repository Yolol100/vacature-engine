import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reviewOnce,pollWithRetry,MAX_REVIEW} from '../src/actions-review.mjs';

const reg='REGISTER',radar='RADAR';
const env={GOOGLE_SERVICE_ACCOUNT_JSON:'test-only-sentinel',VACATURE_REGISTER_ID:reg,RADAR_RESULT_ID:radar,RADAR_BASELINE_MIN_RECORDS:'1'};
const sourceKeys=['greenhouse','company-automattic','lever','company-kinsta','ashby','company-zapier'];

function cells() {
  return {
    "'Config'!A1:B":[['key','value'],['radar_enabled','FALSE'],['radar_delivery','none'],['radar_state_branch','radar-state']],
    "'Bronnen'!A1:A":[['source_id'],...sourceKeys.map(x=>[x])],
    "'Bronnen'!M1:M":[['status'],...sourceKeys.map(()=>['active'])],
    "'Vacatures'!A1:B":[['vacancy_id','status']],
    "'Vacatures'!G1:H":[['canonical_url','official_url']],
    "'Applications'!A1:A":[['vacancy_id']],
    "'Applications'!C1:C":[['status']],
    "'Applications'!E1:E":[['application_url']],
    "'ApplicationEvents'!A1:B":[['event_id','vacancy_id']],
    "'ApplicationEvents'!D1:D":[['event_type']],
    "'ApplicationEvents'!F1:F":[['status_after']],
    "'Nieuwe vacatures'!A1:A":[['observation_key']],
    "'Nieuwe vacatures'!F1:F":[['officiele_url']],
    "'Radar State'!A1:A":[['identity'],['greenhouse:automatticcareers:baseline']],
    "'Radar State'!C1:C":[['official_url'],['https://boards.greenhouse.io/automatticcareers/jobs/baseline']],
    "'Radar State'!D1:D":[['status'],['baseline']]
  };
}
function job(n) {
  const url='https://boards.greenhouse.io/automatticcareers/jobs/'+n;
  return {identity:'greenhouse:automatticcareers:'+n,source_id:'greenhouse',
    source_account:'automatticcareers',source_job_id:String(n),employer:'Automattic',
    title:'WordPress Developer '+n,url,source_url:url,location:'Remote',remote:'remote'};
}
function harness(overrides={}) {
  const data=overrides.data||cells();
  const jobs=overrides.jobs||[job('one')];
  const calls={read:0,poll:0};
  const readRanges=async (_id,ranges)=>{
    calls.read++;
    if(overrides.failRead)throw new Error('Sheets read HTTP 503');
    return ranges.map(range=>{
      if(!Object.hasOwn(data,range))throw new Error('Unknown fixture range');
      return data[range];
    });
  };
  const publicJobs=async source=>{
    calls.poll++;
    if(overrides.failATS&&source.source_id==='greenhouse')throw new Error('Public API HTTP 503');
    return source.source_id==='greenhouse'?jobs:[];
  };
  const run=(maxCandidates=5,environment=env)=>reviewOnce({
    env:environment,accessToken:async()=> 'mock-token',
    readRanges,publicJobs,maxCandidates
  });
  return {data,jobs,calls,run};
}

test('one official ATS observation reaches only manual review; no writes',async()=>{
  const h=harness(),r=await h.run();
  assert.equal(r.status,'review_ready');
  assert.equal(r.mode,'read_only');
  assert.equal(r.manual_review_required,true);
  assert.equal(r.candidates.length,1);
  assert.equal(r.baseline_records_read,1);
  assert.equal(r.google_sheet_rows_written,0);
  assert.equal(r.application_submissions,0);
  assert.equal(h.calls.read,7);
});
test('zero fresh positions returns an empty, successful manual queue',async()=>{
  const r=await harness({jobs:[]}).run();
  assert.equal(r.status,'review_ready');
  assert.equal(r.candidates.length,0);
});
test('hard stop at 10 review observations',async()=>{
  const r=await harness({jobs:Array.from({length:23},(_,i)=>job(i+1))}).run(10);
  assert.equal(r.counts.observed,23);
  assert.equal(r.candidates.length,10);
  assert.equal(MAX_REVIEW,10);
});
test('reject invalid limit and an invalid auth secret before reading',async()=>{
  const h=harness();
  await assert.rejects(()=>h.run(11),/Invalid candidate limit/);
  await assert.rejects(()=>h.run(5,{...env,GOOGLE_SERVICE_ACCOUNT_JSON:''}),/Missing required/);
  assert.equal(h.calls.read,0);
});
test('inactive ATS + employer pair is not visited',async()=>{
  const h=harness();
  h.data["'Bronnen'!M1:M"][1]=['retired'];
  const r=await h.run();
  assert.equal(r.candidates.length,0);
  assert.equal(r.active_sources,2);
  assert.equal(h.calls.poll,2);
});
test('no eligible source fails closed',async()=>{
  const h=harness();
  for(let i=1;i<h.data["'Bronnen'!M1:M"].length;i++)
    h.data["'Bronnen'!M1:M"][i]=['retired'];
  await assert.rejects(()=>h.run(),/No active registered source pair/);
});
test('already shown role in Vacatures suppresses review candidate',async()=>{
  const h=harness(),j=h.jobs[0];
  h.data["'Vacatures'!A1:B"].push(['historic-id','shown']);
  h.data["'Vacatures'!G1:H"].push([j.url,j.url]);
  const r=await h.run();
  assert.equal(r.counts.already_in_register,1);
  assert.equal(r.candidates.length,0);
});
test('submitted application with matching vacancy ID is suppressed',async()=>{
  const h=harness(),j=h.jobs[0];
  h.data["'Vacatures'!A1:B"].push(['submitted-id','submitted']);
  h.data["'Vacatures'!G1:H"].push([j.url,j.url]);
  h.data["'Applications'!A1:A"].push(['submitted-id']);
  h.data["'Applications'!C1:C"].push(['submitted']);
  h.data["'Applications'!E1:E"].push([j.url]);
  const r=await h.run();
  assert.equal(r.counts.previously_applied,1);
});
test('submitted application with absent vacancy ID but exact official URL is suppressed',async()=>{
  const h=harness(),j=h.jobs[0];
  h.data["'Applications'!A1:A"].push(['']);
  h.data["'Applications'!C1:C"].push(['submitted']);
  h.data["'Applications'!E1:E"].push([j.url]);
  const r=await h.run();
  assert.equal(r.counts.previously_applied,1);
  assert.equal(r.candidates.length,0);
});
test('previously delivered Radar result suppresses repeated official identity',async()=>{
  const h=harness(),j=h.jobs[0];
  h.data["'Nieuwe vacatures'!A1:A"].push([j.identity]);
  h.data["'Nieuwe vacatures'!F1:F"].push([j.url]);
  const r=await h.run();
  assert.equal(r.counts.previously_seen,1);
  assert.equal(r.candidates.length,0);
});
test('existing baseline official URL suppresses resurfacing',async()=>{
  const h=harness({jobs:[job('baseline')]});
  const r=await h.run();
  assert.equal(r.counts.previously_seen,1);
});
test('duplicate exact official URL never yields duplicate manual review entries',async()=>{
  const j=job(1);const h=harness({jobs:[j,j]});
  const r=await h.run();
  assert.equal(r.candidates.length,1);
  assert.equal(r.counts.previously_seen,1);
});
test('Google read failure fails closed before any official ATS source polling',async()=>{
  const h=harness({failRead:true});
  await assert.rejects(()=>h.run(),/Sheets read HTTP 503/);
  assert.equal(h.calls.poll,0);
});
test('transient official ATS failure is partial, never a zero-results success',async()=>{
  const r=await harness({failATS:true}).run();
  assert.equal(r.status,'partial');
  assert.equal(r.failures[0].reason,'Public API HTTP 503');
});
test('unexpected official ATS job URL cannot reach review queue',async()=>{
  const j={...job(1),url:'https://fraud.invalid/apply/1'};
  const r=await harness({jobs:[j]}).run();
  assert.equal(r.status,'partial');
  assert.equal(r.candidates.length,0);
});
test('mismatched register headers fail before ATS polling',async()=>{
  const h=harness();h.data["'Vacatures'!G1:H"][0][1]='bad_name';
  await assert.rejects(()=>h.run(),/Spreadsheet header mismatch/);
  assert.equal(h.calls.poll,0);
});
test('duplicate identities in Radar State halt rather than silently replacing history',async()=>{
  const h=harness();
  h.data["'Radar State'!A1:A"].push(['greenhouse:automatticcareers:baseline']);
  h.data["'Radar State'!C1:C"].push(['https://boards.greenhouse.io/automatticcareers/jobs/baseline']);
  h.data["'Radar State'!D1:D"].push(['baseline']);
  await assert.rejects(()=>h.run(),/Duplicate identity/);
});
test('two identical read-only attempts neither change nor lose baseline',async()=>{
  const h=harness(),a=await h.run(),b=await h.run();
  assert.deepEqual(a,b);
  assert.equal(h.data["'Radar State'!A1:A"].length,2);
});
test('workflow has no scheduled runner or privileged writes',()=>{
  const yml=readFileSync('../.github/workflows/vacature-radar.yml','utf8');
  assert.ok(yml.includes('workflow_dispatch:'));
  assert.ok(yml.includes('issues:'));
  assert.ok(yml.includes('github.event.issue.user.login'));
  assert.ok(yml.includes('queue: max'));
  assert.ok(!yml.includes('cancel-in-progress: true'));
  assert.ok(yml.includes('checkpoint-review:'));
  assert.ok(yml.includes("vars.RADAR_PERSIST_APPROVED == 'yes'"));
  assert.ok(!yml.includes('live-radar:'));
  assert.ok(!/^\s+schedule:/m.test(yml));
  assert.ok(/^\s+contents: write/m.test(yml),'only the doubly approved checkpoint job has write permission');
  assert.ok(!/^\s+pull-requests: write/m.test(yml));
});

test('live Config blocks candidate processing when old delivery or new radar is enabled',async()=>{
  const h=harness();
  h.data["'Config'!A1:B"][1][1]='TRUE';
  await assert.rejects(()=>h.run(),/read-only transition state/);
  assert.equal(h.calls.poll,0);
  h.data["'Config'!A1:B"][1][1]='FALSE';
  h.data["'Config'!A1:B"][2][1]='email';
  await assert.rejects(()=>h.run(),/read-only transition state/);
  assert.equal(h.calls.poll,0);
});
test('missing historical baseline fails closed, no ATS fetch',async()=>{
  const h=harness();
  h.data["'Radar State'!A1:A"]=[['identity']];
  h.data["'Radar State'!C1:C"]=[['official_url']];
  h.data["'Radar State'!D1:D"]=[['status']];
  await assert.rejects(()=>h.run(),/Radar State baseline unavailable/);
  assert.equal(h.calls.poll,0);
});
test('inconsistent public ATS source identity is rejected',async()=>{
  const j={...job(1),identity:'greenhouse:automatticcareers:other-id'};
  const r=await harness({jobs:[j]}).run();
  assert.equal(r.status,'partial');
  assert.equal(r.candidates.length,0);
});
test('candidate log fields are strictly bounded',async()=>{
  const j={...job(1),title:'WordPress Developer '+'X'.repeat(5000)};
  const r=await harness({jobs:[j]}).run();
  assert.equal(r.candidates.length,1);
  assert.ok(r.candidates[0].title.length<=240);
});
test('a live baseline minimum larger than available observations blocks read-only review',async()=>{
  const h=harness();
  await assert.rejects(()=>h.run(5,{...env,RADAR_BASELINE_MIN_RECORDS:'26'}),/Radar State baseline unavailable/);
});

test('two concurrent read-only commands produce the same results without state writes',async()=>{
  const h=harness();
  const [first,second]=await Promise.all([h.run(),h.run()]);
  assert.deepEqual(first,second);
  assert.equal(first.application_submissions+second.application_submissions,0);
  assert.equal(first.google_sheet_rows_written+second.google_sheet_rows_written,0);
  assert.equal(h.data["'Radar State'!A1:A"].length,2);
});
test('retry after an interrupted transient ATS request remains read-only and safe',async()=>{
  const data=cells(),j=job('new-after-error');
  let n=0;
  const readRanges=async(_id,ranges)=>ranges.map(range=>data[range]);
  const args={env,accessToken:async()=> 'mock-token',readRanges,
    publicJobs:async source=>{
      if(source.source_id!=='greenhouse')return [];
      n++;
      if(n<=2)throw new Error('Public API HTTP 503');
      return [j];
    }};
  const first=await reviewOnce(args);
  const second=await reviewOnce(args);
  assert.equal(first.status,'partial');
  assert.equal(second.status,'review_ready');
  assert.equal(second.candidates.length,1);
  assert.equal(second.google_sheet_rows_written,0);
});
test('candidate count from empty official feeds is not exaggerated into verified vacancies',async()=>{
  const r=await harness({jobs:[]}).run();
  assert.equal(r.candidates.length,0);
  assert.equal(r.manual_review_required,true);
  assert.ok(!Object.hasOwn(r,'verified_vacancies'));
});

test('duplicated live source ID stops review even if one status is active',async()=>{
  const h=harness();
  h.data["'Bronnen'!A1:A"].push(['greenhouse']);
  h.data["'Bronnen'!M1:M"].push(['active']);
  await assert.rejects(()=>h.run(),/Duplicate source ID/);
  assert.equal(h.calls.poll,0);
});

test('live state branch policy drift fails closed before official ATS requests',async()=>{
  const h=harness();
  h.data["'Config'!A1:B"][3][1]='other-state';
  await assert.rejects(()=>h.run(),/read-only transition state/);
  assert.equal(h.calls.poll,0);
});

test('one transient public ATS 5xx is retried once then succeeds',async()=>{
  let calls=0,delays=[];
  const fn=async()=>{
    calls++;
    if(calls===1)throw Object.assign(new Error('Public API HTTP 503'),{status:503});
    return [job('retried')];
  };
  const rows=await pollWithRetry({source_id:'greenhouse'},fn,ms=>{delays.push(ms);});
  assert.equal(calls,2);
  assert.equal(rows.length,1);
  assert.deepEqual(delays,[300]);
});
test('persistent 5xx is not retried without bound',async()=>{
  let calls=0;
  await assert.rejects(()=>pollWithRetry({},async()=>{
    calls++;throw Object.assign(new Error('Public API HTTP 502'),{status:502});
  },async()=>{}),/Public API HTTP 502/);
  assert.equal(calls,2);
});
test('HTTP 429 is never immediately retried against provider rate limits',async()=>{
  let calls=0;
  await assert.rejects(()=>pollWithRetry({},async()=>{
    calls++;throw Object.assign(new Error('Public API HTTP 429'),{status:429,retryAfterSeconds:60});
  },async()=>{}),/Public API HTTP 429/);
  assert.equal(calls,1);
});
test('long Retry-After on 5xx is honored by deferring entire source',async()=>{
  let calls=0;
  await assert.rejects(()=>pollWithRetry({},async()=>{
    calls++;throw Object.assign(new Error('Public API HTTP 503'),{status:503,retryAfterSeconds:45});
  },async()=>{}),/Public API HTTP 503/);
  assert.equal(calls,1);
});
test('invalid ATS payload is not retried under the transient HTTP policy',async()=>{
  let calls=0;
  await assert.rejects(()=>pollWithRetry({},async()=>{
    calls++;throw new Error('Unexpected public jobs payload');
  },async()=>{}),/Unexpected public jobs payload/);
  assert.equal(calls,1);
});
