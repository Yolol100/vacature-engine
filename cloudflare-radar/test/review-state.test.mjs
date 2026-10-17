import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {
  parseReviewState,commitReviewReceipt,receiptDigest,
  MAX_REVIEW_STATE_ITEMS
} from '../src/review-state.mjs';
import {reviewOnce} from '../src/actions-review.mjs';

const role=n=>({
  observation_key:'ashby:zapier:'+n,
  official_url:'https://jobs.ashbyhq.com/zapier/'+n,
  title:'WordPress Developer '+n
});
const result=(candidates=[role('one')])=>({
  status:'review_ready',mode:'read_only',
  manual_review_required:true,google_sheet_rows_written:0,
  application_submissions:0,failures:[],candidates
});
const options={runId:'100',result:result(),now:'2026-10-17T01:00:00.000Z'};
test('empty technical history defaults to schema 1, not a new data controller',()=>{
  assert.deepEqual(parseReviewState(),{schema_version:1,observed:[],runs:[]});
  assert.deepEqual(parseReviewState(''),parseReviewState());
});
test('valid complete review creates one deterministic technical receipt',()=>{
  const a=commitReviewReceipt(undefined,options);
  assert.equal(a.added,1);
  assert.equal(a.state.observed[0].identity,role('one').observation_key);
  assert.equal(a.state.runs[0].run_id,'100');
  assert.equal(a.state.runs[0].digest.length,64);
  assert.equal(a.state.observed[0].first_seen_utc,options.now);
  assert.equal(a.state.observed[0].official_url,role('one').official_url);
});
test('repeating the same run ID with the same payload does not duplicate data',()=>{
  const first=commitReviewReceipt(undefined,options);
  const again=commitReviewReceipt(first.state,options);
  assert.equal(again.added,0);
  assert.equal(again.already_committed,true);
  assert.deepEqual(again.state,first.state);
});
test('same run ID with modified candidates is a hard replay conflict',()=>{
  const previous=commitReviewReceipt(undefined,options);
  assert.throws(()=>commitReviewReceipt(previous.state,
    {...options,result:result([role('two')])}),/Conflicting radar review replay/);
});
test('new runs do not duplicate existing job identities',()=>{
  const previous=commitReviewReceipt(undefined,options);
  const next=commitReviewReceipt(previous.state,{
    runId:'101',result:result([role('one'),role('two')]),
    now:'2026-10-17T01:02:00.000Z'
  });
  assert.equal(next.added,1);
  assert.equal(next.state.observed.length,2);
  assert.equal(next.state.runs.length,2);
});
test('different provider identities with the same exact role URL do not create two observations',()=>{
  const previous=commitReviewReceipt(undefined,options);
  const conflicting=role('other');conflicting.official_url=role('one').official_url;
  const next=commitReviewReceipt(previous.state,{runId:'102',result:result([conflicting])});
  assert.equal(next.added,0);
  assert.equal(next.state.observed.length,1);
});
test('same identity with different URL is a hard conflict',()=>{
  const previous=commitReviewReceipt(undefined,options);
  const conflicting=role('one');
  conflicting.official_url=role('two').official_url;
  assert.throws(()=>commitReviewReceipt(previous.state,{runId:'103',
    result:result([conflicting])}),/Conflicting radar identity/);
});
test('partial ATS failure blocks persistence without modifying initial history',()=>{
  const r=result();r.status='partial';
  assert.throws(()=>commitReviewReceipt(undefined,{runId:'104',result:r}),/Unsafe or partial/);
});
test('not-reviewed or automatic submission records cannot be made durable',()=>{
  for(const changes of [
    {manual_review_required:false},{application_submissions:1},
    {google_sheet_rows_written:1},{mode:'write'},
    {failures:[{reason:'source_http_503'}]}
  ]){
    assert.throws(()=>commitReviewReceipt(undefined,{
      runId:'105',result:{...result(),...changes}
    }),/Unsafe or partial/);
  }
});
test('reject malformed run IDs and unauditable times',()=>{
  assert.throws(()=>commitReviewReceipt(undefined,{...options,runId:'abc'}),/Invalid radar run ID/);
  assert.throws(()=>commitReviewReceipt(undefined,{...options,now:'not-a-date'}),/Invalid review timestamp/);
});
test('garbled, duplicated, or mutated technical history fails closed',()=>{
  const good=commitReviewReceipt(undefined,options).state;
  assert.throws(()=>parseReviewState('{bad-json'));
  assert.throws(()=>parseReviewState({...good,unknown:'field'}),/Invalid radar review state/);
  assert.throws(()=>parseReviewState({...good,observed:[...good.observed,...good.observed]}),/duplicate review observation/);
  assert.throws(()=>parseReviewState({...good,runs:[...good.runs,...good.runs]}),/duplicate review receipt/);
  assert.throws(()=>parseReviewState({...good,observed:[{...good.observed[0],
    applicant_email:'secret@example.invalid'}]}),/Invalid or duplicate review observation/);
});
test('invalid URLs and oversized candidate data cannot become stored observations',()=>{
  const r=result([{...role('one'),official_url:'http://example.invalid/x'}]);
  assert.throws(()=>commitReviewReceipt(undefined,{runId:'106',result:r}));
  const r2=result([{...role('one'),title:'x'.repeat(5000)}]);
  assert.throws(()=>commitReviewReceipt(undefined,{runId:'107',result:r2}));
});
test('empty verified poll is a durable zero-candidate technical receipt only',()=>{
  const receipt=commitReviewReceipt(undefined,{runId:'108',result:result([])});
  assert.equal(receipt.added,0);
  assert.equal(receipt.state.runs.length,1);
  assert.equal(receipt.state.observed.length,0);
});
test('review history size never increases beyond safety cap',()=>{
  const prior=parseReviewState();
  prior.observed=Array.from({length:MAX_REVIEW_STATE_ITEMS},(_,n)=>({
    identity:'ashby:zapier:'+String(n).padStart(5,'0'),
    official_url:'https://jobs.ashbyhq.com/zapier/'+String(n).padStart(5,'0'),
    title:'WordPress Developer',first_seen_utc:options.now
  }));
  assert.throws(()=>commitReviewReceipt(prior,options),/Radar review state capacity reached/);
});
test('hashes are stable across response ordering and exclude secret material',()=>{
  assert.equal(receiptDigest(result([role('one'),role('two')])),
    receiptDigest(result([role('two'),role('one')])));
  assert.equal(receiptDigest(result([role('one')])),
    receiptDigest({...result([role('one')]),secret:'must-not-be-hashed'}));
});
test('only the existing radar-state branch is identified for technical persistence',()=>{
  const yml=readFileSync('../.github/workflows/vacature-radar.yml','utf8');
  assert.match(yml,/radar-state/);
  assert.match(yml,/queue: max/);
  assert.doesNotMatch(yml,/^\s+schedule:/m);
  assert.match(yml,/inputs\.persist_review/);
  assert.doesNotMatch(yml,/legacy_first_seen|live-radar:/);
});

test('Personio and Workable receipts require genuine tenant-specific job URLs',()=>{
  const samples=[
    {observation_key:'personio:syde:2345',
     official_url:'https://syde.jobs.personio.com/job/2345',
     title:'Senior WordPress Engineer'},
    {observation_key:'workable:awesomemotive:ABC123',
     official_url:'https://apply.workable.com/awesomemotive/j/ABC123',
     title:'WordPress Developer'}
  ];
  const receipt=commitReviewReceipt(undefined,{runId:'220',
    result:result(samples),now:options.now});
  assert.equal(receipt.added,2);
  assert.equal(receipt.state.observed.length,2);
  const malicious={...samples[1],official_url:'https://evil.invalid/awesomemotive/j/ABC123'};
  assert.throws(()=>commitReviewReceipt(undefined,{
    runId:'221',result:result([malicious])
  }),/Invalid radar review candidate/);
});

test('verified employer-owned Greenhouse roles can be replayed without duplicates',()=>{
  const jobs=[
    {observation_key:'greenhouse:digitalocean98:8249366',
     official_url:'https://www.digitalocean.com/careers/position/apply?gh_jid=8249366',
     title:'WordPress Engineer'},
    {observation_key:'greenhouse:pantheon:8202241',
     official_url:'https://pantheon.io/about/careers/detail?gh_jid=8202241',
     title:'Senior Web Developer'}
  ];
  const first=commitReviewReceipt(undefined,{runId:'301',result:result(jobs),now:options.now});
  assert.equal(first.added,2);
  assert.equal(parseReviewState(first.state).observed.length,2);
  const second=commitReviewReceipt(first.state,{runId:'301',result:result(jobs),now:options.now});
  assert.equal(second.added,0);
  assert.equal(second.already_committed,true);
  const invalid={...jobs[0],official_url:'https://www.digitalocean.com/careers/position/apply?gh_jid=1234567'};
  assert.throws(()=>commitReviewReceipt(undefined,{runId:'302',
    result:result([invalid]),now:options.now}),/Invalid radar review candidate/);
});
