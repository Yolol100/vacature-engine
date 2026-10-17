import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync,webcrypto} from 'node:crypto';
import {accessToken,readRanges} from '../src/index.mjs';

// Generate disposable credentials entirely in memory. No real accounts, secrets,
// key material or tokens are saved to the repository or Cloudflare.
const privateKey=generateKeyPairSync('rsa',{modulusLength:2048}).privateKey
  .export({type:'pkcs8',format:'pem'});
function account(email){return {GOOGLE_SERVICE_ACCOUNT_JSON:JSON.stringify({
  client_email:email,private_key:privateKey
})};}
const originalFetch=globalThis.fetch;
if(!globalThis.crypto)globalThis.crypto=webcrypto;
function decodeJwt(assertion){
  const part=assertion.split('.')[1];
  return JSON.parse(Buffer.from(part,'base64url').toString('utf8'));
}
test('parallel OAuth requests share one JWT and isolate cache cannot mix credentials',async()=>{
  const calls=[];
  try{
    globalThis.fetch=async(url,opts)=>{
      assert.equal(String(url),'https://oauth2.googleapis.com/token');
      const jwt=decodeJwt(new URLSearchParams(String(opts.body)).get('assertion'));
      calls.push(jwt.iss);
      return new Response(JSON.stringify({
        access_token:'test-token-'+jwt.iss,expires_in:3600
      }),{status:200});
    };
    const one=account('performance-a@example.invalid');
    const results=await Promise.all(Array.from({length:5},()=>accessToken(one)));
    assert.deepEqual(results,Array(5).fill('test-token-performance-a@example.invalid'));
    assert.equal(calls.length,1,'single-flight avoids overlapping OAuth sign/fetch');
    assert.equal(await accessToken(one),results[0]);
    assert.equal(calls.length,1,'fresh token remains isolate-local and reusable');
    const rotated=account('performance-b@example.invalid');
    assert.equal(await accessToken(rotated),'test-token-performance-b@example.invalid');
    assert.deepEqual(calls,['performance-a@example.invalid','performance-b@example.invalid'],
      'rotated credential must not use the previous OAuth token or signing key');
  }finally{globalThis.fetch=originalFetch;}
});
test('failed OAuth never leaves a permanently rejected in-flight promise',async()=>{
  const env=account('performance-failure@example.invalid');
  let attempts=0;
  try{
    globalThis.fetch=async()=>{
      attempts++;
      if(attempts===1)return new Response('',{status:503});
      return new Response(JSON.stringify({access_token:'recovered-token',expires_in:3600}),
        {status:200});
    };
    await assert.rejects(accessToken(env),/Google OAuth HTTP 503/);
    assert.equal(await accessToken(env),'recovered-token');
    assert.equal(attempts,2);
  }finally{globalThis.fetch=originalFetch;}
});
test('Sheets batchGet projects only values but retains range ordering and empties',async()=>{
  try{
    globalThis.fetch=async(url,opts)=>{
      const parsed=new URL(String(url));
      assert.equal(parsed.origin,'https://sheets.googleapis.com');
      assert.equal(parsed.searchParams.get('fields'),'valueRanges(values)');
      assert.deepEqual(parsed.searchParams.getAll('ranges'),[
        "'Bronnen'!A1:A","'Bronnen'!M1:M"
      ]);
      assert.equal(opts.headers.Authorization,'Bearer placeholder-token');
      return new Response(JSON.stringify({valueRanges:[
        {values:[['source_id'],['greenhouse']]},
        {values:[['status'],['active']]}
      ]}),{status:200});
    };
    const actual=await readRanges('not-a-real-id',[
      "'Bronnen'!A1:A","'Bronnen'!M1:M"
    ],'placeholder-token');
    assert.deepEqual(actual,[[['source_id'],['greenhouse']],[['status'],['active']]]);
  }finally{globalThis.fetch=originalFetch;}
});

test('Actions mode uses Sheets read-only OAuth permission and never reuses broad token',async()=>{
  const {readOnlyAccessToken}=await import('../src/google-sheets.mjs');
  const auth=account('actions-read-only@example.invalid');
  const requested=[];
  try{
    globalThis.fetch=async(_url,opts)=>{
      const jwt=decodeJwt(new URLSearchParams(String(opts.body)).get('assertion'));
      requested.push(jwt.scope);
      return new Response(JSON.stringify({
        access_token:'scope-token-'+requested.length,expires_in:3600
      }),{status:200});
    };
    assert.equal(await readOnlyAccessToken(auth),'scope-token-1');
    assert.equal(await readOnlyAccessToken(auth),'scope-token-1');
    assert.equal(await accessToken(auth),'scope-token-2');
    assert.deepEqual(requested,[
      'https://www.googleapis.com/auth/spreadsheets.readonly',
      'https://www.googleapis.com/auth/spreadsheets'
    ]);
    await assert.rejects(
      ()=>accessToken(auth,'https://www.googleapis.com/auth/drive'),
      /Invalid Google OAuth scope/
    );
  }finally{globalThis.fetch=originalFetch;}
});

test('review runner identifies register vs Radar Sheets 403 without leaking raw API details',async()=>{
  const details=[
    ['register',{error:{status:'PERMISSION_DENIED',message:'do-not-log-private-name'}},'PERMISSION_DENIED'],
    ['radar',{error:{status:'PERMISSION_DENIED',message:'hidden-user',
      details:[{reason:'SERVICE_DISABLED'}]}},'SERVICE_DISABLED'],
    ['register',{error:{status:'PERMISSION_DENIED',
      details:[{reason:'ACCESS_TOKEN_SCOPE_INSUFFICIENT'}]}},'SCOPE_INSUFFICIENT'],
    ['radar',{error:{status:'RESOURCE_EXHAUSTED'}},'QUOTA_EXCEEDED']
  ];
  try{
    for(const [book,body,reason] of details){
      globalThis.fetch=async()=>new Response(JSON.stringify(body),{status:403});
      await assert.rejects(()=>readRanges('id',['A1:B4'],'test-token',book),
        error=>error.message==='Sheets read HTTP 403 ['+book+':'+reason+']');
    }
  }finally{globalThis.fetch=originalFetch;}
});
test('Cloudflare legacy Sheets callers keep unchanged generic error and no credential exposure',async()=>{
  try{
    globalThis.fetch=async()=>new Response(JSON.stringify({
      error:{status:'PERMISSION_DENIED',message:'never-log-account'}
    }),{status:403});
    await assert.rejects(()=>readRanges('id',['A1'],'test-token'),
      error=>error.message==='Sheets read HTTP 403');
  }finally{globalThis.fetch=originalFetch;}
});
