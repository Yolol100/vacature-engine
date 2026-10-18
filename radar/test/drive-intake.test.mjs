import test from 'node:test';
import assert from 'node:assert/strict';
import {selectFreshRows,verifiedObservation,registerIndex,INTAKE_HEADERS} from '../src/drive-intake.mjs';
import {normalizeJobs,strongRoleKeys} from '../src/logic.mjs';

const RUN='39145498132',NOW='2026-10-18T16:40:00.000Z';
const url='https://jobs.ashbyhq.com/zapier/04838dc8-0efa-4fe5-b705-c99f6b3f17c6';
const source={source_id:'ashby',account:'zapier',employer:'Zapier'};
function candidate(overrides={}){
  return {
    observation_key:'ashby:zapier:04838dc8-0efa-4fe5-b705-c99f6b3f17c6',
    source_id:'ashby',source_account:'zapier',source_job_id:'04838dc8-0efa-4fe5-b705-c99f6b3f17c6',
    employer:'Zapier',title:'WordPress Automation Specialist',official_url:url,
    location:'Remote, EMEA',remote_text:'Remote',
    confirmed_published_at:'2026-10-18T12:00:00.000Z',
    verification:'official_ats_observed; manual review required',
    ...overrides
  };
}
const emptyIndex=()=>({known:new Set(),applied:new Set()});
const take=(arr,index=emptyIndex(),existingIds=new Set(),existingUrls=new Set())=>
  selectFreshRows({candidates:arr,index,existingIds,existingUrls,now:NOW,runId:RUN});
test('valid official recent role is appended only as unverified Google Radar intake',()=>{
  const rows=take([candidate()]);
  assert.equal(rows.length,1);
  assert.equal(rows[0].length,INTAKE_HEADERS.length);
  assert.equal(rows[0][5],url);
  assert.equal(rows[0][10],'2026-10-18T12:00:00.000Z');
  assert.equal(rows[0][11],NOW);
  assert.equal(rows[0][13],'geen_ingediende_sollicitatie_in_register');
  assert.match(rows[0][14],/nog_te_verifieren/);
  assert.match(rows[0][16],/nog_te_verifieren/);
  assert.equal(rows[0][20],RUN);
});
test('missing, invalid, future and older publication dates never enter fresh intake',()=>{
  for(const time of ['',null,'nonsense','2026-10-01T12:00:00Z','2026-10-19T16:00:00Z']){
    assert.deepEqual(take([candidate({confirmed_published_at:time})]),[]);
  }
});
test('generic full stack/AI engineering roles do not masquerade as WordPress or workflow fit',()=>{
  assert.equal(take([candidate({title:'Full-Stack Engineer (Backend Leaning) - Creative Agents'})]).length,0);
});
test('already applied or already known official URLs are excluded before write',()=>{
  const keys=strongRoleKeys(url);
  assert.ok(keys.length>0);
  assert.equal(take([candidate()],{known:new Set(keys),applied:new Set(keys)}).length,0);
  assert.equal(take([candidate()],{known:new Set(keys),applied:new Set()}).length,0);
  assert.equal(take([candidate()],emptyIndex(),new Set([candidate().observation_key])).length,0);
  assert.equal(take([candidate()],emptyIndex(),new Set(),new Set([url])).length,0);
  assert.equal(take([candidate()],emptyIndex(),new Set(),new Set([url+'?utm_source=board'])).length,0);
});
test('two identical candidate records are idempotent inside one batch',()=>{
  assert.equal(take([candidate(),candidate()]).length,1);
});
test('unknown official provider host aborts instead of entering intake',()=>{
  assert.throws(()=>take([candidate({official_url:'https://fraud.invalid/jobs/1'})]),/candidate_official_url/);
});
test('candidate provenance mismatch aborts',()=>{
  assert.throws(()=>take([candidate({source_account:'other-company'})]),/candidate_contract/);
});
test('official Ashby publishes a date, and first seen must not create a fake date',()=>{
  const jobs=normalizeJobs(source,{jobs:[{
    id:'04838dc8-0efa-4fe5-b705-c99f6b3f17c6',
    title:'WordPress Automation Specialist',jobUrl:url,
    location:'Remote, EMEA',isRemote:true,
    publishedAt:'2026-10-18T12:00:00.000+00:00'
  }]});
  assert.equal(jobs[0].confirmed_published_at,'2026-10-18T12:00:00.000Z');
  assert.equal(normalizeJobs(source,{jobs:[{
    id:'04838dc8-0efa-4fe5-b705-c99f6b3f17c6',
    title:'WordPress Automation Specialist',jobUrl:url,
    location:'Remote',isRemote:true,updatedAt:'2026-10-18T12:00:00Z'
  }]})[0].confirmed_published_at,'');
});
test('legacy ingestion never labels a Lever createdAt as official publication date',()=>{
  const lever=normalizeJobs({source_id:'lever',account:'kinsta',employer:'Kinsta'},[{
    id:'abc',text:'WordPress Developer',hostedUrl:'https://jobs.lever.co/kinsta/abc',
    categories:{location:'Remote'},createdAt:1792320000000,workplaceType:'remote'
  }]);
  assert.equal(lever[0].confirmed_published_at,'');
});
test('observation parser rejects failed or partial upstream sources',()=>{
  const scope={technical_source_scope:{supported:13,source_manifest:'ingestion/source-specs.radar.json'}};
  const output={schema_version:1,status:'review_ready',mode:'read_only',manual_review_required:true,
    register_authoritative:true,application_submissions:0,google_sheet_rows_written:0,
    failures:[],counts:{review_candidates:1},candidates:[candidate()]};
  assert.equal(verifiedObservation(JSON.stringify(scope)+'\n'+JSON.stringify(output)+'\n').length,1);
  assert.throws(()=>verifiedObservation(JSON.stringify(scope)+'\n'+JSON.stringify({...output,status:'partial'})+'\n'),/observation_not_accepted/);
  assert.throws(()=>verifiedObservation(JSON.stringify(scope)+'\n'+JSON.stringify({...output,application_submissions:1})+'\n'),/observation_not_accepted/);
});
test('Register row headers and submitted application events are respected',()=>{
  const ranges=[
    {values:[['vacancy_id','status'],['v123','shown']]},
    {values:[['canonical_url','official_url'],[url,url]]},
    {values:[['vacancy_id'],['v123']]},
    {values:[['status'],['submitted']]},
    {values:[['application_url'],[url]]},
    {values:[['event_id','vacancy_id'],['evt1','v123']]},
    {values:[['event_type'],['submitted']]},
    {values:[['status_after'],['submitted']]}
  ];
  const index=registerIndex(ranges);
  assert.equal(take([candidate()],index).length,0);
  assert.throws(()=>registerIndex([{values:[['untrusted']]}]),/register_ranges/);
});
