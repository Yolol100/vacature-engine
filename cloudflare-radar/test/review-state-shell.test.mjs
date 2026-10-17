// Isolated git integration: no network, credentials, Sheets or D1 writes.
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {execFileSync,spawnSync} from 'node:child_process';

const script=resolve('scripts/persist-review-state.sh');
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
  writeFileSync(join(workspace,'.runtime','review-observations.next.json'),
    '{"schema_version":1,"observed":[],"runs":[]}\n');
  return {root,remote,workspace,head:git(workspace,'rev-parse','radar-state')};
}
function apply(f,overrides={}){
  const env={...process.env,GITHUB_WORKSPACE:f.workspace,GITHUB_EVENT_NAME:'workflow_dispatch',
    GITHUB_ACTOR:'Yolol100',RADAR_PERSIST:'1',RADAR_STATE_BASE_SHA:f.head,...overrides};
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
