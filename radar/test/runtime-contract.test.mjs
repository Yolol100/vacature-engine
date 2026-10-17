import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync,readdirSync} from 'node:fs';
import {join} from 'node:path';

const root=new URL('../../',import.meta.url);
const text=path=>readFileSync(new URL(path,root),'utf8');

test('GitHub Radar has no active Worker, D1, Wrangler or Cloudflare runtime',()=>{
  assert.equal(existsSync(new URL('cloudflare-radar/',root)),false);
  const modules=readdirSync(new URL('radar/src/',root)).filter(p=>p.endsWith('.mjs'));
  assert.equal(modules.length>=8,true);
  for(const module of modules){
    const source=text('radar/src/'+module);
    assert.doesNotMatch(source,/\b(?:RADAR_DB|wrangler|cloudflare:|\.prepare\(|\.scheduled\b)\b/i,module);
  }
  assert.doesNotMatch(text('radar/package.json'),/wrangler|cloudflare/i);
});
test('Google Sheets token is strictly read-only',()=>{
  const source=text('radar/src/google-sheets.mjs');
  assert.match(source,/https:\/\/www\.googleapis\.com\/auth\/spreadsheets\.readonly/);
  assert.doesNotMatch(source,/auth\/spreadsheets['"]/);
  assert.match(source,/export const readOnlyAccessToken=/);
  assert.doesNotMatch(source,/export \{accessToken/);
});
test('review checkpoint requires separately approved owner manual dispatch',()=>{
  const workflow=text('.github/workflows/vacature-radar.yml');
  assert.match(workflow,/github\.actor == 'Yolol100'/);
  assert.match(workflow,/vars\.RADAR_PERSIST_APPROVED == 'yes'/);
  assert.match(workflow,/inputs\.persist_review == true/);
  assert.match(workflow,/contents: write/);
  assert.match(workflow,/run: bash radar\/scripts\/load-review-state\.sh/);
  assert.match(workflow,/run: bash radar\/scripts\/persist-review-state\.sh/);
  assert.doesNotMatch(workflow,/cloudflare-radar/);
});
