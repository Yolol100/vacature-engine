import {PILOT_SOURCES,adapterUrl,canonicalUrl,isValidJob,normalizeJobs,registerKnown,toRadarRow} from './logic.mjs';

// Isolated transport-only radar. No application, eligibility, scoring or user-mailbox access.
const GOOGLE_SCOPE='https://www.googleapis.com/auth/spreadsheets';
const GOOGLE_TOKEN='https://oauth2.googleapis.com/token';
const MAX_JOBS=160;
const OUTBOX_BATCH=20;
let accessTokenCache;
function b64url(bytes) {
  let text='';
  for(const byte of bytes) text+=String.fromCharCode(byte);
  return btoa(text).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
function json64(value){return b64url(new TextEncoder().encode(JSON.stringify(value)));}
function pemBytes(pem) {
  const value=pem.replace(/-----BEGIN PRIVATE KEY-----|-----END PRIVATE KEY-----|\s/g,'');
  return Uint8Array.from(atob(value),c=>c.charCodeAt(0));
}
async function getGoogleToken(env) {
  if(accessTokenCache && accessTokenCache.expires>Date.now()) return accessTokenCache.token;
  const credentials=JSON.parse(env.GOOGLE_SERVICE_ACCOUNT_JSON||'{}');
  if(!credentials.client_email||!credentials.private_key) throw new Error('Google service account is not configured');
  const privateKey=await crypto.subtle.importKey('pkcs8',pemBytes(credentials.private_key),
    {name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['sign']);
  const now=Math.floor(Date.now()/1000);
  const unsigned=json64({alg:'RS256',typ:'JWT'})+'.'+json64({
    iss:credentials.client_email,scope:GOOGLE_SCOPE,aud:GOOGLE_TOKEN,iat:now,exp:now+3300
  });
  const signature=await crypto.subtle.sign('RSASSA-PKCS1-v1_5',privateKey,new TextEncoder().encode(unsigned));
  const form=new URLSearchParams({
    grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',assertion:unsigned+'.'+b64url(new Uint8Array(signature))
  });
  const response=await fetch(GOOGLE_TOKEN,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:form});
  if(!response.ok) throw new Error('Google OAuth HTTP '+response.status);
  const data=await response.json();
  if(!data.access_token) throw new Error('Google OAuth response did not include an access token');
  accessTokenCache={token:data.access_token,expires:Date.now()+Math.max(60,(Number(data.expires_in)||3600)-120)*1000};
  return accessTokenCache.token;
}
async function getRanges(sheetId,ranges,token) {
  const url=new URL('https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(sheetId)+'/values:batchGet');
  for(const range of ranges) url.searchParams.append('ranges',range);
  const response=await fetch(url.toString(),{headers:{Authorization:'Bearer '+token}});
  if(!response.ok) throw new Error('Sheets read HTTP '+response.status);
  const data=await response.json();
  if(!Array.isArray(data.valueRanges)||data.valueRanges.length!==ranges.length) throw new Error('Sheets read incomplete');
  return data.valueRanges.map(x=>x.values||[]);
}
async function appendRows(sheetId,range,rows,token) {
  if(!rows.length) return;
  const url='https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(sheetId)+'/values/'+encodeURIComponent(range)+':append?valueInputOption=RAW&insertDataOption=INSERT_ROWS';
  const response=await fetch(url,{method:'POST',headers:{
    Authorization:'Bearer '+token,'Content-Type':'application/json'
  },body:JSON.stringify({majorDimension:'ROWS',values:rows})});
  if(!response.ok) throw new Error('Sheets append HTTP '+response.status);
  const result=await response.json();
  if(Number(result.updates?.updatedRows)!==rows.length) throw new Error('Sheets write incomplete');
}
async function getPublicJobs(source) {
  const response=await fetch(adapterUrl(source),{headers:{Accept:'application/json'}});
  if(!response.ok) throw new Error('Public API HTTP '+response.status);
  const size=Number(response.headers.get('content-length')||0);
  if(size>2_000_000) throw new Error('Public API response exceeded limit');
  const jobs=normalizeJobs(source,await response.json());
  if(jobs.length>MAX_JOBS) throw new Error('Source exceeds safe job count limit');
  return jobs.filter(isValidJob);
}
function placeholders(count){return Array.from({length:count},()=>'?').join(',');}
async function existingJobKeys(db,jobs) {
  const seen=new Set();
  for(let offset=0;offset<jobs.length;offset+=80) {
    const keys=jobs.slice(offset,offset+80).map(job=>job.identity);
    const query='SELECT identity FROM radar_observations WHERE identity IN ('+placeholders(keys.length)+')';
    const found=await db.prepare(query).bind(...keys).all();
    for(const row of found.results||[]) seen.add(row.identity);
  }
  return seen;
}
async function insertObservations(db,jobs) {
  for(let i=0;i<jobs.length;i+=16){
    const batch=jobs.slice(i,i+16);
    const query='INSERT OR IGNORE INTO radar_observations (identity,source_instance,canonical_url,status,payload_json,first_seen_at) VALUES '+batch.map(()=>' (?,?,?,?,?,?)').join(',');
    const params=batch.flatMap(j=>[j.identity,j.source_instance,j.url,j.status,JSON.stringify(j.row),j.first_seen_at]);
    await db.prepare(query).bind(...params).run();
  }
}
async function setStatuses(db,keys,status) {
  for(let offset=0;offset<keys.length;offset+=60) {
    const batch=keys.slice(offset,offset+60);
    await db.prepare('UPDATE radar_observations SET status=? WHERE identity IN ('+placeholders(batch.length)+')').bind(status,...batch).run();
  }
}
async function acquireLock(db){
  const current=new Date().toISOString();
  const until=new Date(Date.now()+180000).toISOString();
  await db.prepare('INSERT OR IGNORE INTO radar_metadata(name,value) VALUES (?,?)').bind('exclusive_poll_lease','1970-01-01T00:00:00.000Z').run();
  const change=await db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value<?').bind(until,'exclusive_poll_lease',current).run();
  return change.meta?.changes===1?until:null;
}
async function releaseLock(db,token) {
  await db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value=?').bind('1970-01-01T00:00:00.000Z','exclusive_poll_lease',token).run();
}
export async function tick(env){
  if(env.RADAR_ENABLED!=='1') return {status:'disabled'};
  if(!env.RADAR_DB||!env.GOOGLE_SERVICE_ACCOUNT_JSON||!env.VACATURE_REGISTER_ID||!env.RADAR_RESULT_ID) throw new Error('Missing required Worker binding or secret');
  const lease=await acquireLock(env.RADAR_DB);
  if(!lease) return {status:'overlap_skipped'};
  try{
    const start=new Date().toISOString(),runId='cloudflare-'+start;
    const token=await getGoogleToken(env);
    const [registry,vacancies,applications]=await getRanges(env.VACATURE_REGISTER_ID,[
      "'Bronnen'!A1:M","'Vacatures'!A1:J","'Applications'!A1:E"
    ],token);
    const [radarKeys,radarLinks]=await getRanges(env.RADAR_RESULT_ID,[
      "'Nieuwe vacatures'!A1:A","'Nieuwe vacatures'!F1:F"
    ],token);
    const alreadyInSheet=new Set(radarKeys.slice(1).map(r=>r[0]).filter(Boolean));
    const sheetLinks=new Set(radarLinks.slice(1).map(r=>canonicalUrl(r[0])).filter(Boolean));
    const appliedOrKnown=registerKnown(vacancies,applications);
    const statuses=new Map(registry.slice(1).filter(r=>r[0]).map(r=>[r[0],r[12]]));
    const sources=PILOT_SOURCES.filter(s=>statuses.get(s.source_id)==='active'&&statuses.get(s.employer_source_id)==='active');
    if(!sources.length) throw new Error('No active source and employer pairs');
    const metrics={sources:0,observations:0,seeded:0,delivered:0,excluded:0,errors:[]};
    for(const source of sources) {
      const instance=source.source_id+':'+source.account;
      let jobs;
      try{jobs=await getPublicJobs(source);}
      catch(error){metrics.errors.push(instance+': '+String(error.message).slice(0,100));continue;}
      const previous=await env.RADAR_DB.prepare('SELECT value FROM radar_metadata WHERE name=?').bind('seeded:'+instance).first();
      const bootstrap=!previous;
      const oldKeys=await existingJobKeys(env.RADAR_DB,jobs);
      const created=[];
      for(const job of jobs){
        if(oldKeys.has(job.identity)) continue;
        const known=appliedOrKnown.has(job.url)||sheetLinks.has(job.url)||alreadyInSheet.has(job.identity);
        if(known)metrics.excluded++;
        const status=bootstrap?'baseline':known?'excluded':'pending';
        created.push({...job,source_instance:instance,status,first_seen_at:start,row:toRadarRow(job,start,runId)});
      }
      await insertObservations(env.RADAR_DB,created);
      if(bootstrap){
        await env.RADAR_DB.prepare('INSERT OR IGNORE INTO radar_metadata(name,value) VALUES (?,?)').bind('seeded:'+instance,start).run();
        metrics.seeded+=created.length;
      }
      metrics.sources++;
      metrics.observations+=jobs.length;
    }
    // At-least-once durable outbox. Confirm existing sheet rows on retry before any append.
    const pending=await env.RADAR_DB.prepare('SELECT identity,canonical_url,payload_json FROM radar_observations WHERE status=? ORDER BY first_seen_at LIMIT ?').bind('pending',OUTBOX_BATCH).all();
    const exclude=[],append=[],plannedUrls=new Set();
    for(const item of pending.results||[]){
      if(alreadyInSheet.has(item.identity)||sheetLinks.has(item.canonical_url)||appliedOrKnown.has(item.canonical_url)||plannedUrls.has(item.canonical_url)){
        exclude.push(item.identity); continue;
      }
      append.push(item); plannedUrls.add(item.canonical_url);
    }
    if(exclude.length) await setStatuses(env.RADAR_DB,exclude,'excluded');
    if(append.length){
      await appendRows(env.RADAR_RESULT_ID,"'Nieuwe vacatures'!A:U",append.map(item=>JSON.parse(item.payload_json)),token);
      await setStatuses(env.RADAR_DB,append.map(item=>item.identity),'delivered');
      metrics.delivered=append.length;
    }
    const completed=new Date().toISOString();
    if(new Date(start).getUTCMinutes()===0||metrics.errors.length||metrics.delivered){
      await appendRows(env.RADAR_RESULT_ID,'Runs!A:L',[[runId,start,completed,metrics.sources,metrics.observations,metrics.delivered,0,metrics.excluded,metrics.seeded,metrics.errors.length,metrics.errors.length?'partial':'ok',metrics.errors.join('; ').slice(0,500)]],token);
    }
    return {status:metrics.errors.length?'partial':'ok',sources:metrics.sources,new_records:metrics.delivered,errors:metrics.errors.length};
  } finally {
    await releaseLock(env.RADAR_DB,lease);
  }
}
export default {
  async scheduled(_event,env,ctx) {
    ctx.waitUntil(tick(env).then(result=>console.log(JSON.stringify(result))).catch(error=>{
      console.error('vacature_radar_tick_failed:'+String(error.message).slice(0,160));
      throw error;
    }));
  },
  async fetch(){return new Response('Not found',{status:404});}
};
