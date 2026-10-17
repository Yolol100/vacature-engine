// Isolated git integration: no network, credentials, Sheets or D1 writes.
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,copyFileSync,rmSync,chmodSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {execFileSync,spawnSync} from 'node:child_process';

const script=resolve('scripts/persist-review-state.sh');
const loadScript=resolve('scripts/load-review-state.sh');
function git(cwd,...args){return execFileSync('git',args,{cwd,encoding:'utf8'}).trim();}
function fixture(){
  const root=mkdtempSync(join(tmpdir(),'radar-git-'));
  const remote=join(root,'remote.git'),workspace=join(root,'workspace');
  mkdirSync(workspace,{recursive:true});
  execFileSync('git',['init','--bare','--quiet',remote]);
  execFileSync('git',['init','--quiet','-b','main',workspace]);
  git(workspace,'config','user.email','test@example.invalid');
  git(workspace,'config','user.name','radar-fixture');
  writeFileSync(join(workspace,'README.md'),'Technical state fixture\n');
  git(workspace,'add','README.md');
  git(workspace,'commit','-m','fixture main');
  git(workspace,'branch','radar-state');
  git(workspace,'remote','add','origin',remote);
  git(workspace,'push','-u','origin','main');
  git(workspace,'switch','radar-state');
  writeFileSync(join(workspace,'state.sqlite3'),'simulated historical binary');
  writeFileSync(join(workspace,'radar-ack.json'),'{"acked_keys":[]}\n');
  git(workspace,'add','state.sqlite3','radar-ack.json');
  git(workspace,'commit','-m','historical state');
  git(workspace,'push','origin','radar-state');
  git(workspace,'switch','main');
  mkdirSync(join(workspace,'.runtime'));
  mkdirSync(join(workspace,'radar','src'),{recursive:true});
  copyFileSync(resolve('src/review-state.mjs'),join(workspace,'radar','src','review-state.mjs'));
  copyFileSync(resolve('src/logic.mjs'),join(workspace,'radar','src','logic.mjs'));
  writeFileSync(join(workspace,'.runtime','review-observations.next.json'),
    '{"schema_version":1,"observed":[],"runs":[]}\n');
  return {root,remote,workspace,head:git(workspace,'rev-parse','radar-state')};
}
function apply(f,overrides={}){
  const env={...process.env,GITHUB_WORKSPACE:f.workspace,GITHUB_EVENT_NAME:'workflow_dispatch',
    GITHUB_ACTOR:'Yolol100',RADAR_PERSIST:'1',RADAR_APPROVED_PERSIST:'yes',RADAR_STATE_BASE_SHA:f.head,...overrides};
  return spawnSync('bash',[script],{cwd:f.workspace,env,encoding:'utf8'});
}
test('one new technical checkpoint commits to existing state branch and reads back exactly',()=>{
  const f=fixture();
  try{
    const first=apply(f);
    assert.equal(first.status,0,first.stderr+' '+first.stdout);
    const after=git(f.workspace,'rev-parse','refs/remotes/origin/radar-state');
    assert.notEqual(after,f.head);
    const persisted=git(f.workspace,'show','refs/remotes/origin/radar-state:review-observations.json');
    assert.equal(persisted,readFileSync(join(f.workspace,'.runtime/review-observations.next.json'),'utf8').trim());
    assert.equal(git(f.workspace,'show','refs/remotes/origin/radar-state:state.sqlite3'),'simulated historical binary');
    assert.equal(git(f.workspace,'show','refs/remotes/origin/radar-state:radar-ack.json'),'{"acked_keys":[]}');
  }finally{rmSync(f.root,{recursive:true,force:true});}
});
test('stale base SHA cannot replace a newer technical state and never force pushes',()=>{
  const f=fixture();
  try{
    const first=apply(f);
    assert.equal(first.status,0,first.stderr);
    const hash=git(f.workspace,'rev-parse','refs/remotes/origin/radar-state');
    const stale=apply(f);
    assert.notEqual(stale.status,0);
    assert.match(stale.stdout,/branch moved/);
    assert.equal(git(f.workspace,'rev-parse','refs/remotes/origin/radar-state'),hash);
  }finally{rmSync(f.root,{recursive:true,force:true});}
});
test('re-applying identical state with current head is no-op, not extra branch commit',()=>{
  const f=fixture();
  try{
    assert.equal(apply(f).status,0);
    f.head=git(f.workspace,'rev-parse','refs/remotes/origin/radar-state');
    const second=apply(f);
    assert.equal(second.status,0,second.stderr+' '+second.stdout);
    assert.equal(git(f.workspace,'rev-parse','refs/remotes/origin/radar-state'),f.head);
  }finally{rmSync(f.root,{recursive:true,force:true});}
});
test('issue trigger, non-owner, or missing approval context cannot mutate the branch',()=>{
  const f=fixture();
  try{
    for(const changes of [
      {GITHUB_EVENT_NAME:'issues'},
      {GITHUB_ACTOR:'untrusted-bot'},
      {RADAR_PERSIST:'0'},
      {RADAR_APPROVED_PERSIST:'no'},
      {RADAR_APPROVED_PERSIST:''},
      {RADAR_STATE_BASE_SHA:''}
    ]){
      const out=apply(f,changes);
      assert.notEqual(out.status,0);
      assert.equal(git(f.workspace,'rev-parse','refs/remotes/origin/radar-state'),f.head);
    }
  }finally{rmSync(f.root,{recursive:true,force:true});}
});
test('missing durable source branch must not generate a replacement state branch',()=>{
  const f=fixture();
  try{
    git(f.workspace,'push','origin','--delete','radar-state');
    const out=apply(f);
    assert.notEqual(out.status,0);
    const remoteRefs=git(f.workspace,'ls-remote','--heads','origin');
    assert.ok(!remoteRefs.includes('refs/heads/radar-state'));
  }finally{rmSync(f.root,{recursive:true,force:true});}
});

test('loader recovers an empty technical history without creating a remote branch or committing',()=>{
  const f=fixture();
  try{
    const envPath=join(f.workspace,'.runtime','GITHUB_ENV');
    writeFileSync(envPath,'');
    const r=spawnSync('bash',[loadScript],{cwd:f.workspace,
      env:{...process.env,GITHUB_ENV:envPath},encoding:'utf8'});
    assert.equal(r.status,0,r.stderr+' '+r.stdout);
    assert.deepEqual(JSON.parse(readFileSync(join(f.workspace,'.runtime','review-observations.json'),'utf8')),
      {schema_version:1,observed:[],runs:[]});
    assert.equal(git(f.workspace,'rev-parse','refs/remotes/origin/radar-state'),f.head);
    assert.match(readFileSync(envPath,'utf8'),/RADAR_STATE_BASE_SHA=[a-f0-9]{40}/);
  }finally{rmSync(f.root,{recursive:true,force:true});}
});
test('loader reads back an already-committed technical receipt from the same existing branch',()=>{
  const f=fixture();
  try{
    assert.equal(apply(f).status,0);
    const envPath=join(f.workspace,'.runtime','GITHUB_ENV');
    writeFileSync(envPath,'');
    const r=spawnSync('bash',[loadScript],{cwd:f.workspace,
      env:{...process.env,GITHUB_ENV:envPath},encoding:'utf8'});
    assert.equal(r.status,0,r.stderr+' '+r.stdout);
    const actual=readFileSync(join(f.workspace,'.runtime','review-observations.json'),'utf8');
    assert.equal(actual,readFileSync(join(f.workspace,'.runtime','review-observations.next.json'),'utf8'));
  }finally{rmSync(f.root,{recursive:true,force:true});}
});
test('loader fails closed when the historical technical branch does not exist',()=>{
  const f=fixture();
  try{
    git(f.workspace,'push','origin','--delete','radar-state');
    const envPath=join(f.workspace,'.runtime','GITHUB_ENV');
    writeFileSync(envPath,'');
    const r=spawnSync('bash',[loadScript],{cwd:f.workspace,
      env:{...process.env,GITHUB_ENV:envPath},encoding:'utf8'});
    assert.notEqual(r.status,0);
    assert.equal(git(f.workspace,'ls-remote','--heads','origin').includes('refs/heads/radar-state'),false);
  }finally{rmSync(f.root,{recursive:true,force:true});}
});


// Controlled fault injection uses an isolated temp bare Git remote. It kills
// only the fixture's bash runner, never a live GitHub Actions job or radar-state.
function applyKilledAtGitPush(f,phase){
  const bin=join(f.root,'fault-bin');
  mkdirSync(bin);
  const realGit=execFileSync('which',['git'],{encoding:'utf8'}).trim();
  const wrapper=join(bin,'git');
  writeFileSync(wrapper,[
    '#!/bin/sh',
    'if [ "$1" = "push" ]; then',
    '  if [ "$RADAR_TEST_STOP_AT" = "before_push" ]; then',
    '    kill -KILL "$RADAR_TEST_RUNNER_PID"',
    '    exit 137',
    '  fi',
    '  "'+realGit+'" "$@"',
    '  result=$?',
    '  if [ "$result" -eq 0 ] && [ "$RADAR_TEST_STOP_AT" = "after_push" ]; then',
    '    kill -KILL "$RADAR_TEST_RUNNER_PID"',
    '    exit 137',
    '  fi',
    '  exit "$result"',
    'fi',
    'exec "'+realGit+'" "$@"'
  ].join('\n')+'\n');
  chmodSync(wrapper,0o755);
  const env={...process.env,GITHUB_WORKSPACE:f.workspace,
    GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_ACTOR:'Yolol100',
    RADAR_PERSIST:'1',RADAR_APPROVED_PERSIST:'yes',
    RADAR_STATE_BASE_SHA:f.head,RADAR_TEST_STOP_AT:phase,
    PATH:bin+':'+process.env.PATH};
  const command='export RADAR_TEST_RUNNER_PID=$$; exec bash "'+script+'"';
  return spawnSync('bash',['-c',command],
    {cwd:f.workspace,env,encoding:'utf8',timeout:12000});
}
function remoteStateSHA(f){
  return git(f.workspace,'ls-remote','origin','refs/heads/radar-state')
    .split(/\s+/)[0];
}

test('SIGKILL before git push never mutates technical history; a fresh runner retries safely',()=>{
  const f=fixture();
  try{
    const before=remoteStateSHA(f);
    const stopped=applyKilledAtGitPush(f,'before_push');
    assert.notEqual(stopped.status,0,'SIGKILL must interrupt the runner');
    assert.equal(remoteStateSHA(f),before,'a staged-but-not-pushed receipt is not durable');
    const retry=apply(f);
    assert.equal(retry.status,0,retry.stderr+' '+retry.stdout);
    assert.notEqual(remoteStateSHA(f),before);
    assert.equal(git(f.workspace,'show','refs/remotes/origin/radar-state:state.sqlite3'),
      'simulated historical binary');
    assert.equal(git(f.workspace,'show','refs/remotes/origin/radar-state:radar-ack.json'),
      '{"acked_keys":[]}');
  }finally{rmSync(f.root,{recursive:true,force:true});}
});

test('SIGKILL after push but before readback recovers exact state without a duplicate commit',()=>{
  const f=fixture();
  try{
    const before=remoteStateSHA(f);
    const stopped=applyKilledAtGitPush(f,'after_push');
    assert.notEqual(stopped.status,0,'SIGKILL must interrupt the runner');
    const after=remoteStateSHA(f);
    assert.notEqual(after,before,'remote checkpoint must survive runner death');
    const envFile=join(f.workspace,'.runtime','github-env');
    writeFileSync(envFile,'');
    const loaded=spawnSync('bash',[loadScript],{cwd:f.workspace,encoding:'utf8',
      env:{...process.env,GITHUB_ENV:envFile},timeout:12000});
    assert.equal(loaded.status,0,loaded.stderr+' '+loaded.stdout);
    const durable=git(f.workspace,'show',
      'refs/remotes/origin/radar-state:review-observations.json');
    const restored=readFileSync(join(f.workspace,'.runtime','review-observations.json'),'utf8');
    assert.equal(restored.trim(),durable,'new runner loads the committed receipt');
    assert.equal(durable,readFileSync(
      join(f.workspace,'.runtime','review-observations.next.json'),'utf8').trim());
    f.head=after;
    const replay=apply(f);
    assert.equal(replay.status,0,replay.stderr+' '+replay.stdout);
    assert.equal(remoteStateSHA(f),after,'replay cannot create an extra commit');
    assert.equal(git(f.workspace,'show','refs/remotes/origin/radar-state:state.sqlite3'),
      'simulated historical binary');
    assert.equal(git(f.workspace,'show','refs/remotes/origin/radar-state:radar-ack.json'),
      '{"acked_keys":[]}');
  }finally{rmSync(f.root,{recursive:true,force:true});}
});
