import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import reviewWorker from '../src/review-worker.mjs';
import compatibilityWorker,{accessToken as legacyToken,readRanges as legacyRanges}
  from '../src/index.mjs';
import {accessToken,readRanges} from '../src/google-sheets.mjs';

const file=name=>readFileSync(new URL(name,import.meta.url),'utf8');

test('the ONE deployed Worker uses review-only entrypoint; legacy tick is never bundled',()=>{
  const cfg=JSON.parse(file('../wrangler.jsonc'));
  assert.equal(cfg.name,'vacature-radar');
  assert.equal(cfg.main,'src/review-worker.mjs');
  assert.deepEqual(cfg.triggers.crons,['* * * * *']);
  assert.equal(cfg.vars.RADAR_ENABLED,'0');
  assert.equal(cfg.vars.RADAR_PIPELINE_MODE,'off');
  const entry=file('../src/review-worker.mjs');
  assert.doesNotMatch(entry,/from ['"]\.\/index\.mjs['"]/);
  assert.doesNotMatch(entry,/\b(?:tick|appendRows|updateCells|insertJobs)\s*\(/);
  assert.match(entry,/RADAR_ENABLED!=='1'/);
  assert.match(entry,/RADAR_PIPELINE_MODE!=='staged_review'/);
  assert.match(entry,/async fetch\(\)/);
  assert.equal(reviewWorker.fetch,compatibilityWorker.fetch);
  assert.equal(reviewWorker.scheduled,compatibilityWorker.scheduled);
});

test('legacy tests and active Worker use the same OAuth and Sheets implementations',()=>{
  assert.equal(legacyToken,accessToken);
  assert.equal(legacyRanges,readRanges);
  const auth=file('../src/google-sheets.mjs');
  assert.match(auth,/crypto\.subtle\.importKey/);
  assert.match(auth,/keyPromise/);
  assert.doesNotMatch(auth,/RADAR_DB|radar_metadata|putMeta/);
});

test('only approved read-only helper imports can reach the live entry',()=>{
  const worker=file('../src/review-worker.mjs');
  const allowed=[
    './google-sheets.mjs',
    './official-ats.mjs',
    './staged-review.mjs',
    './health.mjs'
  ];
  const imports=[...worker.matchAll(/from ['"]([^'"]+)['"]/g)].map(m=>m[1]);
  assert.deepEqual(imports.sort(),allowed.sort());
  assert.doesNotMatch(file('../src/official-ats.mjs'),/appendRows|updateCells|submitApplication/);
});
