import test from 'node:test';
import assert from 'node:assert/strict';
import { hashSource, inspectFiles, updatedFiles, synchronize, RADAR_SHEET_ID, REGISTER_ID } from './sync.mjs';

const sample = (version) => `var VACATURE_RADAR = {radarId:'${RADAR_SHEET_ID}',registerId:'${REGISTER_ID}'};\nfunction runVacatureRadar() {return ${version};}\n`;
const manifest = {name:'appsscript', type:'JSON', source:'{"timeZone":"Europe/Amsterdam"}', id:'output-only'};
const sourceFile = (version) => ({name:'Code',type:'SERVER_JS',source:sample(version),functionSet:{functions:[]}});
const otherFile = {name:'Helpers',type:'SERVER_JS',source:'function helper() {}', id:'retain-content'};
const env = {
  RADAR_SCRIPT_ID:'12345678901234567890__', RADAR_GOOGLE_CLIENT_ID:'dummy-client',
  RADAR_GOOGLE_CLIENT_SECRET:'dummy-secret', RADAR_GOOGLE_REFRESH_TOKEN:'dummy-refresh'
};
function mockGoogle({files = [sourceFile(1),otherFile,manifest],parentId=RADAR_SHEET_ID,
  drift=false,refusePut=false}={}) {
  let live=structuredClone(files);
  const calls=[];
  let getCount=0;
  const fetchImpl=async (url, opts) => {
    calls.push({url,method:opts.method});
    const reply=(body,status=200)=>({ok:status===200,status,async json(){return structuredClone(body)}});
    if (url==='https://oauth2.googleapis.com/token') return reply({access_token:'test-access-token'});
    if (url.endsWith(`/projects/${env.RADAR_SCRIPT_ID}`)) return reply({scriptId:env.RADAR_SCRIPT_ID,parentId});
    if (url.endsWith('/content') && opts.method === 'GET') {
      getCount++;
      if (drift && getCount === 2) live[0].source=sample(9);
      return reply({files:live});
    }
    if (url.endsWith('/content') && opts.method === 'PUT') {
      if (refusePut) return reply({error:'not allowed'},403);
      live=JSON.parse(opts.body).files;
      return reply({files:live});
    }
    throw new Error('Unexpected mocked request');
  };
  return {fetchImpl,calls,get files(){return live}};
}

test('rejects malformed, ambiguous and missing project files', () => {
  assert.throws(()=>inspectFiles({files:[sourceFile(1),sourceFile(1),manifest]}),/duplicate/i);
  assert.throws(()=>inspectFiles({files:[otherFile,manifest]}),/uniquely/i);
  assert.throws(()=>inspectFiles({files:[sourceFile(1),otherFile]}),/manifest/i);
  assert.throws(()=>inspectFiles({files:[sourceFile(1),{...manifest,source:'bad-json'}]}),/manifest/i);
  assert.throws(()=>inspectFiles({files:[{...sourceFile(1),source:'function runVacatureRadar(){}'},manifest]}),/expected Vacature Radar/i);
});

test('preserves every unrelated source file and manifest exactly', () => {
  const snap=inspectFiles({files:[sourceFile(1),otherFile,manifest]});
  const proposed=updatedFiles(snap,sample(2));
  assert.equal(proposed.length,3);
  assert.equal(proposed[0].source,sample(2));
  assert.equal(proposed[1].source,otherFile.source);
  assert.equal(proposed[2].source,manifest.source);
  assert.deepEqual(Object.keys(proposed[0]).sort(),['name','source','type']);
  assert.notEqual(hashSource(sample(1)),hashSource(sample(2)));
});

test('inspect reports hashes without any remote writes', async () => {
  const fake=mockGoogle();const logs=[];
  const result=await synchronize({mode:'inspect',env,fetchImpl:fake.fetchImpl,
    readSource:async()=>sample(2),log:(s)=>logs.push(s)});
  assert.equal(result.state,'INSPECTED');
  assert.equal(result.liveHash,hashSource(sample(1)));
  assert.match(logs.join(' '),/DIFFERENT/);
  assert.equal(fake.calls.some((c)=>c.method==='PUT'),false);
});

test('deploy refuses to write without exact approved remote hash', async () => {
  const fake=mockGoogle();
  await assert.rejects(synchronize({mode:'deploy',env,fetchImpl:fake.fetchImpl,
    readSource:async()=>sample(2),log:()=>{}}),/Expected live SHA256/i);
  assert.equal(fake.calls.some((c)=>c.method==='PUT'),false);
  assert.equal(fake.files[0].source,sample(1));
});

test('deploy changes only scanner file with matching hash and verifies readback', async () => {
  const fake=mockGoogle();
  const result=await synchronize({mode:'deploy',
    env:{...env,RADAR_EXPECTED_LIVE_SHA256:hashSource(sample(1))},
    fetchImpl:fake.fetchImpl,readSource:async()=>sample(2),log:()=>{}});
  assert.equal(result.state,'DEPLOYED');
  assert.equal(fake.files[0].source,sample(2));
  assert.deepEqual(fake.files[1],{name:otherFile.name,type:otherFile.type,source:otherFile.source});
  assert.equal(fake.files[2].source,manifest.source);
  assert.equal(fake.calls.filter((c)=>c.method==='PUT').length,1);
});

test('identical live code never writes even when hash approval is absent', async () => {
  const fake=mockGoogle();
  const result=await synchronize({mode:'deploy',env,fetchImpl:fake.fetchImpl,
    readSource:async()=>sample(1),log:()=>{}});
  assert.equal(result.state,'NO_CHANGE');
  assert.equal(fake.calls.some((c)=>c.method==='PUT'),false);
});

test('cannot deploy to an unrelated project or standalone script', async () => {
  const fake=mockGoogle({parentId:'unrelated-document'});
  await assert.rejects(synchronize({mode:'deploy',
    env:{...env,RADAR_EXPECTED_LIVE_SHA256:hashSource(sample(1))},
    fetchImpl:fake.fetchImpl,readSource:async()=>sample(2),log:()=>{}}),/not the expected/i);
  assert.equal(fake.calls.some((c)=>c.method==='PUT'),false);
});

test('cannot overwrite content changed after the initial inspection', async () => {
  const fake=mockGoogle({drift:true});
  await assert.rejects(synchronize({mode:'deploy',
    env:{...env,RADAR_EXPECTED_LIVE_SHA256:hashSource(sample(1))},
    fetchImpl:fake.fetchImpl,readSource:async()=>sample(2),log:()=>{}}),/changed during preflight/i);
  assert.equal(fake.calls.some((c)=>c.method==='PUT'),false);
});

test('failed Google API write is not treated as success', async () => {
  const fake=mockGoogle({refusePut:true});
  await assert.rejects(synchronize({mode:'deploy',
    env:{...env,RADAR_EXPECTED_LIVE_SHA256:hashSource(sample(1))},
    fetchImpl:fake.fetchImpl,readSource:async()=>sample(2),log:()=>{}}),/HTTP 403/);
  assert.equal(fake.files[0].source,sample(1));
});

test('missing secrets stop before any remote contact', async () => {
  const fake=mockGoogle();
  await assert.rejects(synchronize({mode:'inspect',env:{},fetchImpl:fake.fetchImpl,
    readSource:async()=>sample(2),log:()=>{}}),/Missing required GitHub secret/);
  assert.equal(fake.calls.length,0);
});
