import {
  PILOT_SOURCES,adapterUrl,buildRegisterIndex,canonicalUrl,chooseSource,cooldownMinutes,
  isValidJob,matchRegister,normalizeJobs,preliminaryInterest,runStatsRow,sourceActive,strongRoleKeys,toRadarRow
} from './logic.mjs';
import {runOneTimeSmokeTest} from './selftest.mjs';
import {runReliabilityProbe,safeDiagnosticError} from './reliability.mjs';
import {monitoredTick} from './health.mjs';

// Standalone transport-only radar; no application submission and no eligibility claims.
const GOOGLE_SCOPE='https://www.googleapis.com/auth/spreadsheets';
const TOKEN_URL='https://oauth2.googleapis.com/token';
const MAX_SOURCE_JOBS=160;
const OUTBOX_SIZE=20;
const MAX_RECONCILIATIONS=20;
const MAX_DB_INSERT_ROWS=16; // 16 * 6 bindings = 96 (under D1's 100 per statement).
const POLL_LOCK_MS=180000;
const TIMEOUT_MS=10000;
let tokenCache;

function b64url(bytes){
  let text='';
  for(const byte of bytes)text+=String.fromCharCode(byte);
  return btoa(text).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
function encodeJSON(value){return b64url(new TextEncoder().encode(JSON.stringify(value)));}
function privateKeyBytes(pem){
  const stripped=pem.replace(/-----BEGIN PRIVATE KEY-----|-----END PRIVATE KEY-----|\s/g,'');
  return Uint8Array.from(atob(stripped),c=>c.charCodeAt(0));
}
async function accessToken(env){
  if(tokenCache&&tokenCache.expires>Date.now())return tokenCache.token;
  const svc=JSON.parse(env.GOOGLE_SERVICE_ACCOUNT_JSON||'{}');
  if(!svc.private_key||!svc.client_email)throw new Error('Missing Google Sheets service account secret');
  const key=await crypto.subtle.importKey('pkcs8',privateKeyBytes(svc.private_key),
    {name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['sign']);
  const now=Math.floor(Date.now()/1000);
  const assertion=encodeJSON({alg:'RS256',typ:'JWT'})+'.'+encodeJSON({
    iss:svc.client_email,scope:GOOGLE_SCOPE,aud:TOKEN_URL,iat:now,exp:now+3300
  });
  const signature=await crypto.subtle.sign('RSASSA-PKCS1-v1_5',key,new TextEncoder().encode(assertion));
  const reply=await fetch(TOKEN_URL,{
    method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:new URLSearchParams({grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion:assertion+'.'+b64url(new Uint8Array(signature))}),signal:AbortSignal.timeout(TIMEOUT_MS)
  });
  if(!reply.ok)throw new Error('Google OAuth HTTP '+reply.status);
  const payload=await reply.json();
  if(!payload.access_token)throw new Error('Missing Google OAuth access token');
  tokenCache={token:payload.access_token,expires:Date.now()+Math.max(60,(Number(payload.expires_in)||3600)-120)*1000};
  return tokenCache.token;
}
async function readRanges(id,ranges,token){
  const url=new URL('https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(id)+'/values:batchGet');
  for(const range of ranges)url.searchParams.append('ranges',range);
  const response=await fetch(url,{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(TIMEOUT_MS)});
  if(!response.ok)throw new Error('Sheets read HTTP '+response.status);
  const body=await response.json();
  if(!Array.isArray(body.valueRanges)||body.valueRanges.length!==ranges.length)throw new Error('Sheets response incomplete');
  return body.valueRanges.map(item=>item.values||[]);
}
async function appendRows(id,range,rows,token){
  if(!rows.length)return;
  const uri='https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(id)+'/values/'+encodeURIComponent(range)+':append?valueInputOption=RAW&insertDataOption=INSERT_ROWS';
  const resp=await fetch(uri,{
    method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
    body:JSON.stringify({majorDimension:'ROWS',values:rows}),signal:AbortSignal.timeout(TIMEOUT_MS)
  });
  if(!resp.ok)throw new Error('Sheets append HTTP '+resp.status);
  const body=await resp.json();
  if(Number(body.updates?.updatedRows)!==rows.length)throw new Error('Incomplete Sheets append');
}
async function updateCells(id,changes,token){
  if(!changes.length)return;
  const uri='https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(id)+'/values:batchUpdate';
  const resp=await fetch(uri,{
    method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
    body:JSON.stringify({valueInputOption:'RAW',data:changes.map(({range,value})=>({range,majorDimension:'ROWS',values:[[value]]}))}),
    signal:AbortSignal.timeout(TIMEOUT_MS)
  });
  if(!resp.ok)throw new Error('Sheets update HTTP '+resp.status);
  const json=await resp.json();
  if(Number(json.totalUpdatedCells)!==changes.length)throw new Error('Incomplete Sheets reconciliation');
}
async function clearSmokeCell(id,range,token){
  const uri='https://sheets.googleapis.com/v4/spreadsheets/'+encodeURIComponent(id)+'/values/'+encodeURIComponent(range)+':clear';
  const resp=await fetch(uri,{
    method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
    body:'{}',signal:AbortSignal.timeout(TIMEOUT_MS)
  });
  if(!resp.ok)throw new Error('Sheets clear HTTP '+resp.status);
}
function assertSheetHeaders(registry,vacancies,applications,events,keys,urls,statuses,actions){
  if(registry?.[0]?.[0]!=='source_id'||vacancies?.[0]?.[0]!=='vacancy_id'||
      applications?.[0]?.[0]!=='vacancy_id'||events?.[0]?.[0]!=='event_id'||
      keys?.[0]?.[0]!=='observation_key'||urls?.[0]?.[0]!=='officiele_url'||
      statuses?.[0]?.[0]!=='sollicitatiehistorie'||actions?.[0]?.[0]!=='actie'){
    throw new Error('Spreadsheet header mismatch: stop before dedupe or writes');
  }
}
function params(n){return Array.from({length:n},()=>'?').join(',');}
async function pendingEntries(db){
  return (await db.prepare('SELECT identity,canonical_url,payload_json,source_instance FROM radar_observations WHERE status=? ORDER BY first_seen_at LIMIT ?')
    .bind('pending',OUTBOX_SIZE).all()).results||[];
}
async function existingKeys(db,jobs){
  const existing=new Set();
  for(let i=0;i<jobs.length;i+=60){
    const ids=jobs.slice(i,i+60).map(j=>j.identity);
    if(!ids.length)continue;
    const result=await db.prepare('SELECT identity FROM radar_observations WHERE identity IN ('+params(ids.length)+')')
      .bind(...ids).all();
    for(const row of result.results||[])existing.add(row.identity);
  }
  return existing;
}
async function insertJobs(db,items){
  for(let i=0;i<items.length;i+=MAX_DB_INSERT_ROWS){
    const part=items.slice(i,i+MAX_DB_INSERT_ROWS);
    const sql='INSERT OR IGNORE INTO radar_observations(identity,source_instance,canonical_url,status,payload_json,first_seen_at) VALUES '+
      part.map(()=>'(?,?,?,?,?,?)').join(',');
    await db.prepare(sql).bind(...part.flatMap(item=>[
      item.identity,item.source_instance,item.url,item.status,JSON.stringify(item.row),item.first_seen_at
    ])).run();
  }
}
async function setStatus(db,ids,status){
  for(let i=0;i<ids.length;i+=60){
    const chunk=ids.slice(i,i+60);
    await db.prepare('UPDATE radar_observations SET status=? WHERE identity IN ('+params(chunk.length)+')')
      .bind(status,...chunk).run();
  }
}
async function getMeta(db,name){
  const result=await db.prepare('SELECT value FROM radar_metadata WHERE name=?').bind(name).first();
  return result?.value??null;
}
async function putMeta(db,name,value){
  await db.prepare('INSERT INTO radar_metadata(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value')
    .bind(name,String(value)).run();
}
async function lock(db){
  const start=new Date().toISOString(),end=new Date(Date.now()+POLL_LOCK_MS).toISOString();
  await db.prepare('INSERT OR IGNORE INTO radar_metadata(name,value) VALUES(?,?)')
    .bind('exclusive_poll_lease','1970-01-01T00:00:00.000Z').run();
  const response=await db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value<?')
    .bind(end,'exclusive_poll_lease',start).run();
  return response.meta?.changes===1?end:null;
}
async function unlock(db,token){
  await db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')
    .bind('1970-01-01T00:00:00.000Z','exclusive_poll_lease',token).run();
}
async function publicJobs(source){
  const resp=await fetch(adapterUrl(source),{
    headers:{Accept:'application/json'},signal:AbortSignal.timeout(TIMEOUT_MS)
  });
  if(!resp.ok){
    const error=new Error('Public API HTTP '+resp.status);
    error.status=resp.status;
    const val=resp.headers.get('retry-after');
    if(val){
      const n=Number(val);
      error.retryAfterSeconds=Number.isFinite(n)?n:Math.max(0,(Date.parse(val)-Date.now())/1000);
    }
    throw error;
  }
  const declared=Number(resp.headers.get('content-length')||0);
  if(declared>2_000_000)throw new Error('Source payload too large');
  const body=await resp.text();
  if(body.length>2_000_000)throw new Error('Source payload too large');
  const items=normalizeJobs(source,JSON.parse(body));
  if(items.length>MAX_SOURCE_JOBS)throw new Error('Source exceeds safe job limit');
  const valid=items.filter(isValidJob);
  if(valid.length!==items.length)throw new Error('Unexpected ATS job host: source contract changed');
  return valid;
}
function rowInfo(keyRows,urlRows,statusRows,actionRows){
  const listed=new Set(),strongURLs=new Set(),records=[];
  for(let i=1;i<keyRows.length;i++){
    const identity=keyRows[i]?.[0]||'',url=canonicalUrl(urlRows[i]?.[0]||'');
    if(identity)listed.add(identity);
    for(const key of strongRoleKeys(url))strongURLs.add(key);
    records.push({identity,url,row:i+1,status:statusRows[i]?.[0]||'',action:actionRows[i]?.[0]||''});
  }
  return {listed,strongURLs,records};
}
function reconcileApplied(records,regIndex){
  const changes=[];let count=0;
  for(const row of records){
    if(!row.url||count>=MAX_RECONCILIATIONS)continue;
    if(!strongRoleKeys(row.url).some(key=>regIndex.applied.has(key)))continue;
    const needsStatus=row.status!=='eerder_gesolliciteerd';
    const needsAction=row.action!=='niet_opnieuw_aanbevelen';
    if(!needsStatus&&!needsAction)continue;
    if(needsStatus)changes.push({range:"'Nieuwe vacatures'!N"+row.row,value:'eerder_gesolliciteerd'});
    if(needsAction)changes.push({range:"'Nieuwe vacatures'!R"+row.row,value:'niet_opnieuw_aanbevelen'});
    count++;
  }
  return changes;
}
export async function tick(env){
  if(env.RADAR_ENABLED!=='1')return {status:'disabled'};
  if(!env.RADAR_DB||!env.GOOGLE_SERVICE_ACCOUNT_JSON||!env.VACATURE_REGISTER_ID||!env.RADAR_RESULT_ID)
    throw new Error('Missing required Worker bindings or secrets');
  const lease=await lock(env.RADAR_DB);
  if(!lease)return {status:'overlap_skipped'};
  try{
    const start=new Date().toISOString(),runId='cloudflare-'+start,token=await accessToken(env);
    const [sourcesRows,vacancyRows,applicationRows,eventRows]=await readRanges(env.VACATURE_REGISTER_ID,[
      "'Bronnen'!A1:M","'Vacatures'!A1:H","'Applications'!A1:E","'ApplicationEvents'!A1:F"
    ],token);
    const [keyRows,urlRows,statusRows,actionRows]=await readRanges(env.RADAR_RESULT_ID,[
      "'Nieuwe vacatures'!A1:A","'Nieuwe vacatures'!F1:F",
      "'Nieuwe vacatures'!N1:N","'Nieuwe vacatures'!R1:R"
    ],token);
    assertSheetHeaders(sourcesRows,vacancyRows,applicationRows,eventRows,keyRows,urlRows,statusRows,actionRows);
    const register=buildRegisterIndex(vacancyRows,applicationRows,eventRows);
    const radar=rowInfo(keyRows,urlRows,statusRows,actionRows);
    const metrics={sources:0,observations:0,known:0,applied:0,skipped:0,delivered:0,errors:[]};
    // Reconcile pre-existing rows after the user submits an application later.
    const changes=reconcileApplied(radar.records,register);
    metrics.applied += changes.filter(item=>item.range.startsWith("'Nieuwe vacatures'!N")).length;
    if(changes.length)await updateCells(env.RADAR_RESULT_ID,changes,token);
    const active=PILOT_SOURCES.filter(source=>sourceActive(sourcesRows,source));
    const activeInstances=new Set(active.map(source=>source.source_id+':'+source.account));
    if(!active.length)throw new Error('No active ATS+employer source pairs');
    // One bounded direct source per minute: each of 3 healthy sources every 3 minutes.
    const source=chooseSource(active,Math.floor(Date.now()/60000));
    const instance=source.source_id+':'+source.account;
    const cooldown=await getMeta(env.RADAR_DB,'cooldown:'+instance);
    if(cooldown&&Date.parse(cooldown)>Date.now()){
      metrics.skipped++;
    }else{
      try{
        const all=await publicJobs(source);
        const now=new Date().toISOString();
        const already=await existingKeys(env.RADAR_DB,all);
        const bootstrap=!(await getMeta(env.RADAR_DB,'seeded:'+instance));
        // A transient empty first response must not seed a baseline and turn recovered old jobs into fake new alerts.
        if(bootstrap&&all.length===0)throw new Error('Empty first ATS snapshot: baseline remains unconfirmed');
        const fresh=[];
        for(const job of all){
          if(already.has(job.identity))continue;
          const prev=matchRegister(job,register);
          const sameRadar=radar.listed.has(job.identity)||
            strongRoleKeys(job.url).some(key=>radar.strongURLs.has(key));
          // Only job-role candidates from title receive radar alerts, not all developer roles.
          const relevant=preliminaryInterest(job);
          if(prev.applied)metrics.applied++;
          else if(prev.known||sameRadar)metrics.known++;
          const status=bootstrap?'baseline':prev.applied||prev.known||sameRadar||!relevant?'excluded':'pending';
          fresh.push({...job,source_instance:instance,status,first_seen_at:now,row:toRadarRow(job,now,runId)});
        }
        await insertJobs(env.RADAR_DB,fresh);
        // Only acknowledge a successfully ingested source; do not bootstrap after an API failure.
        if(bootstrap)await putMeta(env.RADAR_DB,'seeded:'+instance,now);
        await putMeta(env.RADAR_DB,'failures:'+instance,0);
        await putMeta(env.RADAR_DB,'cooldown:'+instance,'1970-01-01T00:00:00.000Z');
        metrics.sources=1;
        metrics.observations=all.length;
        if(bootstrap)metrics.skipped+=fresh.length;
      }catch(error){
        const previous=Number(await getMeta(env.RADAR_DB,'failures:'+instance)||0);
        const failures=Math.min(50,previous+1);
        const delay=cooldownMinutes(failures,error.status,Number(error.retryAfterSeconds));
        await putMeta(env.RADAR_DB,'failures:'+instance,failures);
        await putMeta(env.RADAR_DB,'cooldown:'+instance,new Date(Date.now()+delay*60000).toISOString());
        metrics.errors.push(instance+': '+String(error.message).slice(0,110));
      }
    }
    // Durable outbox; retry after errors. Readback-before-append prevents duplicate delivery.
    const pending=await pendingEntries(env.RADAR_DB);
    const duplicates=[],delivered=[],append=[],planned=new Set();
    for(const entry of pending){
      if(!activeInstances.has(entry.source_instance)){
        duplicates.push(entry.identity);
        continue;
      }
      const url=canonicalUrl(entry.canonical_url);
      if(radar.listed.has(entry.identity)){
        delivered.push(entry.identity);continue;
      }
      const reg=matchRegister({url,source_url:url},register);
      const strong=strongRoleKeys(url);
      if(reg.applied||reg.known||strong.some(key=>radar.strongURLs.has(key)||planned.has(key))){
        duplicates.push(entry.identity);
        continue;
      }
      append.push(entry);
      for(const key of strong)planned.add(key);
    }
    if(delivered.length)await setStatus(env.RADAR_DB,delivered,'delivered');
    if(duplicates.length)await setStatus(env.RADAR_DB,duplicates,'excluded');
    if(append.length){
      const values=append.map(entry=>JSON.parse(entry.payload_json));
      await appendRows(env.RADAR_RESULT_ID,"'Nieuwe vacatures'!A:U",values,token);
      await setStatus(env.RADAR_DB,append.map(entry=>entry.identity),'delivered');
      metrics.delivered=append.length;
    }
    const end=new Date().toISOString();
    // Bounded reporting: hourly heartbeat and every material event/failure.
    if(new Date(start).getUTCMinutes()===0||changes.length||metrics.errors.length||metrics.delivered){
      await appendRows(env.RADAR_RESULT_ID,'Runs!A:L',[runStatsRow(runId,start,end,metrics)],token);
    }
    return {status:metrics.errors.length?'partial':metrics.sources===0?'cooldown':'ok',sources:metrics.sources,new_records:metrics.delivered,
      applied_reconciled:changes.filter(x=>x.range.includes('!N')).length,errors:metrics.errors.length};
  }finally{await unlock(env.RADAR_DB,lease);}
}
export default{
  async scheduled(_event,env,ctx){
    const ops={
      accessToken,readRanges,updateCells,clearCell:clearSmokeCell,publicJobs,
      assertSheetHeaders,PILOT_SOURCES,sourceActive
    };
    const work=env.RADAR_ENABLED==='1'
      ? monitoredTick(env,tick)
      : runOneTimeSmokeTest(env,ops).then(outcome=>
        outcome.status==='disabled'?runReliabilityProbe(env,ops):outcome);
    ctx.waitUntil(work.then(outcome=>{
      if(outcome.status!=='disabled'&&outcome.status!=='already_claimed')
        console.log(JSON.stringify(outcome));
    }).catch(error=>{
      console.error('vacature_radar_poll_failed:'+safeDiagnosticError(error));
      throw error;
    }));
  },
  async fetch(){return new Response('Not found',{status:404});}
};
