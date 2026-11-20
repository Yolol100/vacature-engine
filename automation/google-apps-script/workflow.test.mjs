import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, writeFileSync, chmodSync, rmSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const workflow = readFileSync(new URL('../../.github/workflows/vacature-radar-script-sync.yml', import.meta.url), 'utf8');
const regressionWorkflow = readFileSync(new URL('../../.github/workflows/ingestion-tests.yml', import.meta.url), 'utf8');

function stepScript(name) {
  const anchor = '      - name: ' + name + '\n';
  const at = workflow.indexOf(anchor);
  assert.notEqual(at, -1, 'Missing workflow step: ' + name);
  const next = workflow.indexOf('      - name: ', at + anchor.length);
  const run = workflow.indexOf('        run: |\n', at);
  assert.ok(run > at && (next < 0 || run < next), 'Missing script block for: ' + name);
  const output = [];
  for (const line of workflow.slice(run + '        run: |\n'.length).split('\n')) {
    if (line && !line.startsWith('          ')) break;
    output.push(line.startsWith('          ') ? line.slice(10) : line);
  }
  return output.join('\n').trimEnd() + '\n';
}

function inTemp(fn) {
  const dir = mkdtempSync(join(tmpdir(), 'radar-workflow-test-'));
  try { return fn(dir); } finally { rmSync(dir, {recursive:true, force:true}); }
}
function runBash(script, dir, moreEnv={}) {
  const path = join(dir, 'github-env');
  writeFileSync(path, '');
  const result = spawnSync('bash', ['-c', script], {encoding:'utf8',
    env:{...process.env, GITHUB_ENV:path, ...moreEnv}});
  return {status:result.status, output:readFileSync(path, 'utf8'),
    stderr:result.stderr, stdout:result.stdout};
}

test('schedule always selects strict read-only healthcheck, even with deploy input', () => {
  assert.match(workflow, /schedule:\s*\n\s*- cron:\s*'23 4 \* \* 0'/);
  assert.match(workflow, /github\.event_name == 'schedule'/);
  inTemp(dir => {
    for (const mode of ['', 'deploy', 'inspect']) {
      const result=runBash(stepScript('Choose safe mode and expected live hash'),dir,
        {EVENT_NAME:'schedule',USER_MODE:mode, USER_EXPECTED_SHA:'',USER_EXPECTED_GITHUB_SHA:''});
      assert.equal(result.status,0,result.stderr);
      assert.equal(result.output,'RADAR_SYNC_MODE=healthcheck\n');
    }
  });
});

test('manual inspect is read-only and invalid manual deploy is rejected', () => {
  inTemp(dir => {
    const script=stepScript('Choose safe mode and expected live hash');
    const good=runBash(script,dir,{EVENT_NAME:'workflow_dispatch',USER_MODE:'inspect'});
    assert.equal(good.status,0,good.stderr);
    assert.equal(good.output,'RADAR_SYNC_MODE=inspect\n');
    const health=runBash(script,dir,{EVENT_NAME:'workflow_dispatch',USER_MODE:'healthcheck'});
    assert.equal(health.status,0,health.stderr);
    assert.equal(health.output,'RADAR_SYNC_MODE=healthcheck\n');
    const bad=runBash(script,dir,{EVENT_NAME:'workflow_dispatch',USER_MODE:'deploy',
      USER_EXPECTED_SHA:'wrong',USER_EXPECTED_GITHUB_SHA:'wrong'});
    assert.notEqual(bad.status,0);
    assert.equal(bad.output,'');
    assert.match(bad.stdout,/BLOCKED:/);
  });
});

test('every PR to main runs all required checks, including workflow-only changes', () => {
  const events=regressionWorkflow.split('\npermissions:')[0];
  assert.match(events,/\n  pull_request:\n    branches: \[main\]\n/);
  assert.doesNotMatch(events,/\bpaths(?:-ignore)?:/);
  assert.match(regressionWorkflow,/name: Apps Script V8 mock tests \(no network\)/);
  assert.match(regressionWorkflow,/unit-tests \(Python 3\.12\)/);
  assert.match(regressionWorkflow,/python-version: \["3\.11", "3\.12", "3\.13"\]/);
});

test('direct push cannot automatically deploy, merged PR commit provenance is accepted', () => {
  assert.match(workflow,/github\.event_name == 'push'[\s\S]*VACATURE_RADAR_AUTO_DEPLOY == 'true'/);
  assert.match(workflow,/repos\/\$RADAR_REPO\/commits\/\$RADAR_PUSH_SHA\/pulls/);
  assert.match(workflow,/\.merged_at != null and \.base.ref == "main"/);
  inTemp(dir => {
    const bin=join(dir,'bin');
    mkdirSync(bin);
    const gh=join(bin,'gh');
    writeFileSync(gh, '#!/bin/bash\nif [[ "$GH_TEST_RESULT" == "match" ]]; then printf "%s\\n" "$RADAR_PUSH_SHA"; elif [[ "$GH_TEST_RESULT" == "unrelated" ]]; then printf "%s\\n" "unrelated-sha"; fi\n');
    chmodSync(gh, 0o755);
    const script=stepScript('Reject direct pushes for automatic Apps Script deployments');
    const options={PATH:bin+':'+(process.env.PATH||''),RADAR_PUSH_SHA:'abcdef123456',RADAR_REPO:'test/repo'};
    for(const value of ['missing','unrelated']){
      const blocked=runBash(script,dir,{...options,GH_TEST_RESULT:value});
      assert.notEqual(blocked.status,0,value+' should be blocked');
      assert.match(blocked.stdout,/BLOCKED:/);
    }
    const allowed=runBash(script,dir,{...options,GH_TEST_RESULT:'match'});
    assert.equal(allowed.status,0,allowed.stderr);
  });
});


test('least privilege and no live vacancy scan is scheduled by this workflow', () => {
  assert.match(workflow,/permissions:\s*\n  contents: read\s*\n  pull-requests: read/);
  assert.doesNotMatch(workflow,/permissions:[\s\S]{0,100}\bcontents: write/);
  assert.match(workflow,/^  push:\s*\n    branches: \[main\]\s*\n    paths:\s*\n      - automation\/google-apps-script\/Code.gs/m);
  assert.doesNotMatch(workflow,/node automation\/google-apps-script\/Code\.gs/);
});
