// Shared read-only Google Sheets transport. Never persist keys or tokens.
const GOOGLE_SCOPE='https://www.googleapis.com/auth/spreadsheets';
const READ_SCOPE='https://www.googleapis.com/auth/spreadsheets.readonly';
const TOKEN_URL='https://oauth2.googleapis.com/token';
const TIMEOUT_MS=10000;
let tokenCache;
let signingKeyCache;
let pendingToken;
const encoder=new TextEncoder();

function b64url(bytes){
  let text='';
  for(const byte of bytes)text+=String.fromCharCode(byte);
  return btoa(text).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
function encodeJSON(value){return b64url(encoder.encode(JSON.stringify(value)));}
function privateKeyBytes(pem){
  const stripped=pem.replace(/-----BEGIN PRIVATE KEY-----|-----END PRIVATE KEY-----|\s/g,'');
  return Uint8Array.from(atob(stripped),c=>c.charCodeAt(0));
}
async function accessToken(env,scope=GOOGLE_SCOPE){
  if(scope!==GOOGLE_SCOPE&&scope!==READ_SCOPE)throw new Error('Invalid Google OAuth scope');
  const secret=env.GOOGLE_SERVICE_ACCOUNT_JSON||'{}';
  if(tokenCache?.secret===secret&&tokenCache.scope===scope&&tokenCache.expires>Date.now())return tokenCache.token;
  // Multiple scheduled invocations in one isolate should never repeat the
  // same RSA import, signature and OAuth request concurrently.
  if(pendingToken?.secret===secret&&pendingToken.scope===scope)return pendingToken.promise;
  const task=(async()=>{
    let entry=signingKeyCache;
    if(!entry||entry.secret!==secret){
      const svc=JSON.parse(secret);
      if(!svc.private_key||!svc.client_email)
        throw new Error('Missing Google Sheets service account secret');
      // CryptoKey is non-extractable and lives in isolate memory only: no
      // OAuth token, key or raw credential is written to D1, KV or logs.
      entry={secret,email:svc.client_email,keyPromise:crypto.subtle.importKey(
        'pkcs8',privateKeyBytes(svc.private_key),
        {name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['sign']
      )};
      signingKeyCache=entry;
    }
    let key;
    try{key=await entry.keyPromise;}
    catch(error){
      if(signingKeyCache===entry)signingKeyCache=undefined;
      throw error;
    }
    const now=Math.floor(Date.now()/1000);
    const assertion=encodeJSON({alg:'RS256',typ:'JWT'})+'.'+encodeJSON({
      iss:entry.email,scope,aud:TOKEN_URL,iat:now,exp:now+3300
    });
    const signature=await crypto.subtle.sign('RSASSA-PKCS1-v1_5',key,
      encoder.encode(assertion));
    const reply=await fetch(TOKEN_URL,{
      method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:new URLSearchParams({grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',
        assertion:assertion+'.'+b64url(new Uint8Array(signature))}),
      signal:AbortSignal.timeout(TIMEOUT_MS)
    });
    if(!reply.ok)throw new Error('Google OAuth HTTP '+reply.status);
    const payload=await reply.json();
    if(!payload.access_token)throw new Error('Missing Google OAuth access token');
    tokenCache={secret,scope,token:payload.access_token,expires:Date.now()+
      Math.max(60,(Number(payload.expires_in)||3600)-120)*1000};
    return tokenCache.token;
  })();
  pendingToken={secret,scope,promise:task};
  try{return await task;}
  finally{if(pendingToken?.promise===task)pendingToken=undefined;}
}
async function readRanges(id,ranges,token){
  const url=new URL('https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(id)+'/values:batchGet');
  for(const range of ranges)url.searchParams.append('ranges',range);
  // Google supports partial responses: parse just the values, not range metadata.
  url.searchParams.set('fields','valueRanges(values)');
  const response=await fetch(url,{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(TIMEOUT_MS)});
  if(!response.ok)throw new Error('Sheets read HTTP '+response.status);
  const body=await response.json();
  if(!Array.isArray(body.valueRanges)||body.valueRanges.length!==ranges.length)throw new Error('Sheets response incomplete');
  return body.valueRanges.map(item=>item.values||[]);
}
const readOnlyAccessToken=env=>accessToken(env,READ_SCOPE);
export {accessToken,readOnlyAccessToken,readRanges};
