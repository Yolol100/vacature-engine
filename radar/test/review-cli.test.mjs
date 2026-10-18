import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,existsSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {spawnSync} from 'node:child_process';

const entry=resolve('src/actions-review-cli.mjs');
function fixture(){
  const root=mkdtempSync(join(tmpdir(),'radar-cli-'));
  mkdirSync(join(root,'.runtime'));
  const state={schema_version:1,observed:[],runs:[{
    run_id:'123',digest:'a'.repeat(64),
    completed_utc:'2026-10-17T01:00:00.000Z',count:1
  }]};
  writeFileSync(join(root,'.runtime','review-observations.json'),JSON.stringify(state));
  return {root,state};
}
function exec(root,overrides={}){
  const env={...process.env,GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_RUN_ID:'123',
    RADAR_PERSIST:'1',RADAR_APPROVED_PERSIST:'yes',RADAR_MAX_CANDIDATES:'5',
    GOOGLE_SERVICE_ACCOUNT_JSON:'',...overrides};
  return spawnSync(process.execPath,[entry],{cwd:root,env,encoding:'utf8'});
}
test('an already committed interrupted run resumes without OAuth or ATS requests',()=>{
  const {root,state}=fixture();
  try{
    const res=exec(root);
    assert.equal(res.status,0,res.stderr);
    assert.match(res.stdout,/"status":"already_committed"/);
    assert.match(res.stdout,/"external_sources_polled":0/);
    assert.deepEqual(JSON.parse(readFileSync(join(root,'.runtime','review-observations.next.json'),'utf8')),state);
  }finally{rmSync(root,{recursive:true,force:true});}
});
test('new run ID cannot bypass missing authentication or create a technical checkpoint',()=>{
  const {root}=fixture();
  try{
    const res=exec(root,{GITHUB_RUN_ID:'124'});
    assert.notEqual(res.status,0);
    assert.equal(existsSync(join(root,'.runtime','review-observations.next.json')),false);
  }finally{rmSync(root,{recursive:true,force:true});}
});
test('issue commands cannot escalate into persistent checkpoint writes',()=>{
  const {root}=fixture();
  try{
    const res=exec(root,{GITHUB_EVENT_NAME:'issues',RADAR_ISSUE_TITLE:'[radar] review 5'});
    assert.notEqual(res.status,0);
    assert.match(res.stderr,/Unauthorized radar issue command or write mode/);
    assert.equal(existsSync(join(root,'.runtime','review-observations.next.json')),false);
  }finally{rmSync(root,{recursive:true,force:true});}
});
test('unapproved manual persistence fails without touching staged output',()=>{
  const {root}=fixture();
  try{
    const res=exec(root,{RADAR_APPROVED_PERSIST:'no'});
    assert.notEqual(res.status,0);
    assert.match(res.stderr,/not explicitly enabled/);
    assert.equal(existsSync(join(root,'.runtime','review-observations.next.json')),false);
  }finally{rmSync(root,{recursive:true,force:true});}
});

test('owner-approved checkpoint explicitly refuses broad discovery mode',()=>{
  const {root}=fixture();
  try{
    const res=exec(root,{RADAR_DISCOVERY_SCOPE:'tiered'});
    assert.notEqual(res.status,0);
    assert.match(res.stderr,/Discovery-only mode cannot write a technical checkpoint/);
    assert.equal(existsSync(join(root,'.runtime','review-observations.next.json')),false);
  }finally{rmSync(root,{recursive:true,force:true});}
});
test('issue-based expanded discovery never permits checkpoint persistence',()=>{
  const {root}=fixture();
  try{
    const res=exec(root,{GITHUB_EVENT_NAME:'issues',
      RADAR_ISSUE_TITLE:'[radar] discover 5'});
    assert.notEqual(res.status,0);
    assert.match(res.stderr,/Unauthorized radar issue command or write mode/);
    assert.equal(existsSync(join(root,'.runtime','review-observations.next.json')),false);
  }finally{rmSync(root,{recursive:true,force:true});}
});

test('maximum discovery cannot bypass manual owner checkpoint approval',()=>{
 const {root}=fixture();
 try{
  for(const overrides of [
    {RADAR_DISCOVERY_SCOPE:'maximum'},
    {GITHUB_EVENT_NAME:'issues',RADAR_ISSUE_TITLE:'[radar] maximum 5'}
  ]){
    const result=exec(root,overrides);
    assert.notEqual(result.status,0);
    assert.match(result.stderr,/Discovery-only mode cannot write a technical checkpoint|Unauthorized radar issue command or write mode/);
    assert.equal(existsSync(join(root,'.runtime','review-observations.next.json')),false);
  }
 }finally{rmSync(root,{recursive:true,force:true});}
});


test('scheduled and owner-started quarter-hour events pass authorization without state writes',()=>{
  const {root}=fixture();
  const base={RADAR_RUN_MODE:'quarter_hour_readonly',
    GITHUB_WORKFLOW:'Vacature Radar quarter-hour observations',
    GITHUB_RUN_ID:'124',RADAR_PERSIST:'0',RADAR_MAX_CANDIDATES:'10',
    RADAR_DISCOVERY_SCOPE:'official_only'};
  try{
    for(const custom of [
      {GITHUB_EVENT_NAME:'schedule',GITHUB_ACTOR:'github-actions[bot]'},
      {GITHUB_EVENT_NAME:'issues',GITHUB_ACTOR:'Yolol100',
        RADAR_ISSUE_TITLE:'[radar] quarter 10'},
      {GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_ACTOR:'Yolol100'}
    ]){
      const result=exec(root,{...base,...custom});
      // Fixture has deliberately no public source manifest: authorization must
      // pass but the run must fail closed before accessing external resources.
      assert.notEqual(result.status,0);
      assert.doesNotMatch(result.stderr,/Unauthorized quarter-hour read-only event|Unsupported radar event/);
      assert.equal(existsSync(join(root,'.runtime','review-observations.next.json')),false);
    }
  }finally{rmSync(root,{recursive:true,force:true});}
});

test('quarter-hour rejects spoofed owners, events, modes, scopes and persistence',()=>{
  const {root}=fixture();
  const base={RADAR_RUN_MODE:'quarter_hour_readonly',
    GITHUB_WORKFLOW:'Vacature Radar quarter-hour observations',
    GITHUB_EVENT_NAME:'issues',GITHUB_ACTOR:'Yolol100',
    RADAR_ISSUE_TITLE:'[radar] quarter 10',
    RADAR_PERSIST:'0',RADAR_MAX_CANDIDATES:'10',
    RADAR_DISCOVERY_SCOPE:'official_only'};
  try{
    for(const custom of [
      {GITHUB_ACTOR:'other-user'},
      {RADAR_ISSUE_TITLE:'[radar] quarter 100'},
      {GITHUB_WORKFLOW:'Vacature Radar (manual technical review)'},
      {GITHUB_EVENT_NAME:'push'},
      {RADAR_PERSIST:'1'},
      {RADAR_DISCOVERY_SCOPE:'maximum'},
      {RADAR_MAX_CANDIDATES:'5'}
    ]){
      const result=exec(root,{...base,...custom});
      assert.notEqual(result.status,0);
      assert.match(result.stderr,/Unauthorized quarter-hour read-only event/);
      assert.equal(existsSync(join(root,'.runtime','review-observations.next.json')),false);
    }
    const manual=exec(root,{GITHUB_EVENT_NAME:'schedule',RADAR_PERSIST:'0',
      RADAR_RUN_MODE:''});
    assert.notEqual(manual.status,0);
    assert.match(manual.stderr,/Unsupported radar event/);
  }finally{rmSync(root,{recursive:true,force:true});}
});
