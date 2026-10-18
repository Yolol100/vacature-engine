import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {selectTieredSources,orderTieredSources,collectTieredDiscovery} from '../src/tiered-discovery.mjs';
import {canonicalUrl,strongRoleKeys,matchRegister,preliminaryInterest} from '../src/logic.mjs';
import {preliminaryNetherlandsScope,preliminaryRemoteEvidence,pollWithRetry} from '../src/actions-review.mjs';
import {safeDiagnosticError} from '../src/health.mjs';

const specs=JSON.parse(readFileSync('../ingestion/source-specs.deploy.json','utf8'));
const feeds=selectTieredSources(specs);
const config=new Map([
  ['direct_discovery_order','employer_direct,ats,discovery_api,wordpress_discovery,google,job_board,discovery'],
  ['high_source_order','himalayas,we-work-remotely,remote-ok']
]);
const metadata=new Map(feeds.map(x=>[x.source_id,{
  type:x.source_id==='himalayas'?'job_board':x.source_type,
  priority:['himalayas','we-work-remotely','remote-ok'].includes(x.source_id)?'high':'medium',
  status:'active'
}]));
const blankIndex={known:new Set(),applied:new Set()};
const readerParams={
  seenIds:new Set(),seenRoles:new Set(),register:blankIndex,fetchJobs:async()=>[],
  pollWithRetry,preliminaryInterest,preliminaryRemoteEvidence,preliminaryNetherlandsScope,
  matchRegister,strongRoleKeys,canonicalUrl,safeDiagnosticError
};
const job=(source,id='a'.repeat(24),url='https://remoteok.com/remote-jobs/example-wordpress-role')=>({
  source_id:source.source_id,source_account:source.account,source_job_id:id,
  identity:source.source_id+':'+source.account+':'+id,
  title:'Remote WordPress Developer',employer:'Example',url,source_url:url,
  location:'Remote, Europe',remote:'remote'
});

test('tiered public discovery reuses eight registered public non-private providers',()=>{
  assert.equal(feeds.length,8);
  assert.deepEqual(feeds.map(x=>x.source_id),[
    'we-work-remotely','remote-ok','himalayas','jobicy-api','remotive',
    'remote-landers-api','remotejobs-org','arbeitnow-api'
  ]);
  assert.equal(feeds.some(x=>x.account.includes('/')),false);
  assert.throws(()=>selectTieredSources(specs.slice(0,-1)),/Missing approved public discovery adapters/);
  assert.throws(()=>selectTieredSources([...specs,...specs.slice(-1)]),
    /Invalid public discovery source contract/);
  const malicious=specs.map(x=>x.source_id==='remote-ok'?
    {...x,endpoint:'https://evil.invalid/private'}:x);
  assert.throws(()=>selectTieredSources(malicious),/Invalid public discovery endpoint/);
});

test('live Config orders available API sources before boards; skips retired IDs',()=>{
  const {enabled,skipped}=orderTieredSources(feeds,metadata,config);
  assert.deepEqual(enabled.map(x=>x.source_id),[
    'arbeitnow-api','jobicy-api','remote-landers-api','remotejobs-org',
    'remotive','himalayas','we-work-remotely','remote-ok'
  ]);
  assert.deepEqual(skipped,[]);
  const blocked=new Map(metadata);blocked.set('remote-ok',{...metadata.get('remote-ok'),status:'retired'});
  const smaller=orderTieredSources(feeds,blocked,config);
  assert.equal(smaller.enabled.some(x=>x.source_id==='remote-ok'),false);
  assert.equal(smaller.skipped[0].reason,'inactive_or_unregistered');
  assert.throws(()=>orderTieredSources(feeds,metadata,new Map([
    ['direct_discovery_order','job_board,discovery_api']
  ])),/Invalid live discovery policy/);
});

test('read-only discovery returns unverified leads only and stops after manual queue fills',async()=>{
  const {enabled}=orderTieredSources(feeds,metadata,config);
  const seenIds=new Set(),seenRoles=new Set(),calls=[];
  const result=await collectTieredDiscovery({...readerParams,sources:enabled,
    seenIds,seenRoles,maxCandidates:1,
    fetchJobs:async source=>{calls.push(source.source_id);return [job(source)];}});
  assert.equal(result.status,'review_ready');
  assert.equal(result.mode,'discovery_only');
  assert.equal(result.candidates.length,1);
  assert.equal(result.candidates[0].source_id,'arbeitnow-api');
  assert.equal(result.candidates[0].verification.startsWith('discovery_only;'),true);
  assert.equal(Object.hasOwn(result.candidates[0],'official_url'),false);
  assert.equal(result.stopped_when_manual_queue_full,true);
  assert.equal(result.not_polled_sources.length,7);
  assert.deepEqual(calls,['arbeitnow-api']);
});

test('cross-feed URL duplicates, register submissions and foreign-only locations never fill review queue',async()=>{
  const {enabled}=orderTieredSources(feeds,metadata,config);
  const applied='https://example.com/jobs/submitted-wordpress';
  const existing='https://example.com/jobs/old-wordpress';
  const index={known:new Set(strongRoleKeys(existing)),applied:new Set(strongRoleKeys(applied))};
  const result=await collectTieredDiscovery({...readerParams,sources:enabled.slice(0,2),
    register:index,maxCandidates:5,fetchJobs:async source=>[
      job(source,'1'.repeat(24),applied),
      job(source,'2'.repeat(24),existing),
      {...job(source,'3'.repeat(24)),location:'Remote - United States'},
      job(source,'4'.repeat(24),'https://example.com/jobs/new-wordpress')
    ]});
  assert.equal(result.status,'review_ready');
  assert.equal(result.counts.previously_applied,2);
  assert.equal(result.counts.already_in_register,2);
  assert.equal(result.counts.geography_outside_nl,2);
  assert.equal(result.candidates.length,1);
  assert.equal(result.counts.previously_seen,1);
});

test('invalid public discovery contract is rejected before accepting any source batch',async()=>{
  const source=feeds[0];
  const result=await collectTieredDiscovery({...readerParams,
    sources:[source],maxCandidates:5,
    fetchJobs:async()=>[job(source),{...job(source),url:'http://localhost/private'}]});
  assert.equal(result.status,'partial');
  assert.equal(result.candidates.length,0);
  assert.equal(result.checked_sources.length,0);
  assert.equal(result.failures[0].reason,'Unexpected public discovery payload');
});

test('country-only API discovery does not fill the manual Netherlands review queue',async()=>{
  const source=feeds.find(x=>x.source_id==='jobicy-api');
  const rows=['LATAM','Hungary','Serbia','Americas','Europe'].map((location,i)=>({
    ...job(source,String(i+1).repeat(24).slice(0,24),
      'https://jobicy.com/jobs/wordpress-'+i),
    location
  }));
  const result=await collectTieredDiscovery({...readerParams,
    sources:[source],maxCandidates:5,seenIds:new Set(),seenRoles:new Set(),
    fetchJobs:async()=>rows});
  assert.equal(result.counts.geography_outside_nl,4);
  assert.equal(result.candidates.length,1);
  assert.equal(result.candidates[0].location,'Europe');
  assert.equal(result.status,'review_ready');
});

test('maximum manual mode visits all eight approved feeds even after review queue is full',async()=>{
  const {enabled}=orderTieredSources(feeds,metadata,config);
  const ids=[],result=await collectTieredDiscovery({...readerParams,
    sources:enabled,maxCandidates:1,scanAll:true,seenIds:new Set(),seenRoles:new Set(),
    fetchJobs:async source=>{ids.push(source.source_id);return [job(source,ids.length.toString(16).padStart(24,'0'),
      'https://example.com/jobs/'+source.source_id)];}
  });
  assert.equal(ids.length,8);
  assert.equal(result.checked_sources.length,8);
  assert.deepEqual(result.not_polled_sources,[]);
  assert.equal(result.stopped_when_manual_queue_full,false);
  assert.equal(result.candidates.length,1);
  assert.equal(result.eligible_not_queued,7);
  assert.equal(result.status,'review_ready');
});
