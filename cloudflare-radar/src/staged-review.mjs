// Phase 1 of the Free-tier migration: resumable review-only Cron.
// All business records and Google Sheets are read-only in this pipeline.
// The legacy delivery path is not invoked. Release requires a separate gate.
import {
  PILOT_SOURCES,activeSourcePairs,buildRegisterIndex,canonicalUrl,
  matchRegister,preliminaryInterest,strongRoleKeys
} from './logic.mjs';

export const STAGE_CONTROL='micro:v1:control';
export const STAGE_RECEIPT='micro:v1:receipt';
export const STAGE_CURSOR='micro:v1:cursor';
export const STAGES=Object.freeze([
  'source_gate','vacancy_history','application_history','radar_history',
  'official_ats','review_only'
]);
const TTL_MS=12*60*1000;
const MAX_SNAPSHOT_BYTES=210000;
const MAX_JOBS=160;
const MAX_CANDIDATES=160;

function saneError(error) {
  const str=String(error?.message||'');
  if (/^(Source gate header mismatch|Vacature Register header mismatch|Application header mismatch|ApplicationEvents header mismatch|Radar header mismatch|No active registered source pair|Official source has no seeded baseline|Unexpected source account|Unexpected source payload|Empty source response|Too many source jobs|Stage snapshot too large|Missing or stale staged snapshot|Invalid stage state|Stage race|Stage data malformed)$/.test(str))
    return str;
  if (/^(Sheets read HTTP|Google OAuth HTTP|Public API HTTP) [45]\d\d$/.test(str))
    return str.slice(0,100);
  return 'Unexpected staged pipeline failure';
}
async function getMeta(db,key) {
  return (await db.prepare('SELECT value FROM radar_metadata WHERE name=?').bind(key).first())?.value??null;
}
async function putMeta(db,key,value) {
  const data=JSON.stringify(value);
  if(data.length>MAX_SNAPSHOT_BYTES)throw new Error('Stage snapshot too large');
  await db.prepare('INSERT INTO radar_metadata(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value')
    .bind(key,data).run();
}
async function changeControl(db,expected,next) {
  const result=await db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')
    .bind(next,STAGE_CONTROL,expected).run();
  if(result.meta?.changes!==1)throw new Error('Stage race');
}
function parse(raw) {
  try {return JSON.parse(raw);} catch {return null;}
}
function snapshotName(cycle,step){return 'micro:v1:snapshot:'+cycle+':'+step;}
async function clearSnapshots(db,cycle){
  for(const stage of STAGES.slice(0,-1)){
    await db.prepare('DELETE FROM radar_metadata WHERE name=?')
      .bind(snapshotName(cycle,stage)).run();
  }
}

function makeCycle(now,cursor) {
  return {
    version:1,run:'cycle_'+now+'_'+cursor,phase:0,cursor,
    started_at:new Date(now).toISOString(),expires_at:new Date(now+TTL_MS).toISOString()
  };
}
function mergeColumns(chunks,columns) {
  const n=Math.max(0,...chunks.map(x=>x.length));
  const output=[];
  for(let i=0;i<n;i++){
    const row=[];
    for(const [index,offset,width] of columns){
      const src=chunks[index]?.[i]||[];
      for(let j=0;j<width;j++)if(src[j]!==undefined)row[offset+j]=src[j];
    }
    output.push(row);
  }
  return output;
}
function headers(rows,pairs,reason) {
  if(pairs.some(([col,expected])=>rows[0]?.[col]!==expected))throw new Error(reason);
}
function stateSnapshot(raw,cycle) {
  const value=parse(raw);
  if(value?.cycle!==cycle||!value.data)throw new Error('Missing or stale staged snapshot');
  return value.data;
}
async function readStage(db,cycle,stage) {
  return stateSnapshot(await getMeta(db,snapshotName(cycle,stage)),cycle);
}
async function storeStage(db,cycle,stage,data) {
  await putMeta(db,snapshotName(cycle,stage),{cycle,data});
}

async function readSourceGate(env,ops,cycle,cursor){
  const token=await ops.accessToken(env);
  const chunks=await ops.readRanges(env.VACATURE_REGISTER_ID,
    ["'Bronnen'!A1:A","'Bronnen'!M1:M"],token);
  if(chunks.length!==2)throw new Error('Stage data malformed');
  const rows=mergeColumns(chunks,[[0,0,1],[1,12,1]]);
  headers(rows,[[0,'source_id'],[12,'status']],'Source gate header mismatch');
  const active=activeSourcePairs(rows,PILOT_SOURCES);
  if(!active.length)throw new Error('No active registered source pair');
  const selected=active[cursor%active.length];
  return {cycle,source:selected.source_id+':'+selected.account,source_id:selected.source_id,
    account:selected.account,active_count:active.length};
}
async function readVacancyHistory(env,ops,cycle){
  const token=await ops.accessToken(env);
  const chunks=await ops.readRanges(env.VACATURE_REGISTER_ID,
    ["'Vacatures'!A1:B","'Vacatures'!G1:H"],token);
  if(chunks.length!==2)throw new Error('Stage data malformed');
  const rows=mergeColumns(chunks,[[0,0,2],[1,6,2]]);
  headers(rows,[[0,'vacancy_id'],[1,'status'],[6,'canonical_url'],[7,'official_url']],'Vacature Register header mismatch');
  return {cycle,rows,read_at:new Date().toISOString()};
}
async function readApplicationHistory(env,ops,cycle,db){
  const vacancy=await readStage(db,cycle,'vacancy_history');
  const token=await ops.accessToken(env);
  const chunks=await ops.readRanges(env.VACATURE_REGISTER_ID,[
    "'Applications'!A1:A","'Applications'!C1:C","'Applications'!E1:E",
    "'ApplicationEvents'!A1:B","'ApplicationEvents'!D1:D","'ApplicationEvents'!F1:F"
  ],token);
  if(chunks.length!==6)throw new Error('Stage data malformed');
  const apps=mergeColumns(chunks.slice(0,3),[[0,0,1],[1,2,1],[2,4,1]]);
  const events=mergeColumns(chunks.slice(3),[[0,0,2],[1,3,1],[2,5,1]]);
  headers(apps,[[0,'vacancy_id'],[2,'status'],[4,'application_url']],'Application header mismatch');
  headers(events,[[0,'event_id'],[1,'vacancy_id'],[3,'event_type'],[5,'status_after']],'ApplicationEvents header mismatch');
  const index=buildRegisterIndex(vacancy.rows,apps,events);
  return {cycle,known:[...index.known],applied:[...index.applied],
    read_at:new Date().toISOString()};
}
async function readRadarHistory(env,ops,cycle){
  const token=await ops.accessToken(env);
  const chunks=await ops.readRanges(env.RADAR_RESULT_ID,[
    "'Nieuwe vacatures'!A1:A","'Nieuwe vacatures'!F1:F",
    "'Nieuwe vacatures'!N1:N","'Nieuwe vacatures'!R1:R"
  ],token);
  if(chunks.length!==4)throw new Error('Stage data malformed');
  const header=['observation_key','officiele_url','sollicitatiehistorie','actie'];
  for(let i=0;i<4;i++)if(chunks[i]?.[0]?.[0]!==header[i])throw new Error('Radar header mismatch');
  const listed=new Set(),strong=new Set();
  for(let i=1;i<chunks[0].length;i++){
    const key=chunks[0][i]?.[0],url=canonicalUrl(chunks[1]?.[i]?.[0]||'');
    if(key)listed.add(key);
    for(const role of strongRoleKeys(url))strong.add(role);
  }
  return {cycle,listed:[...listed],role_keys:[...strong],read_at:new Date().toISOString()};
}
async function readOfficialSource(env,ops,cycle,db) {
  const gate=await readStage(db,cycle,'source_gate');
  const source=PILOT_SOURCES.find(x=>x.source_id===gate.source_id&&x.account===gate.account);
  if(!source||source.source_id+':'+source.account!==gate.source)
    throw new Error('Unexpected source account');
  if(!await getMeta(db,'seeded:'+gate.source))
    throw new Error('Official source has no seeded baseline');
  const jobs=await ops.publicJobs(source);
  if(!Array.isArray(jobs)||jobs.length>MAX_JOBS)throw new Error('Too many source jobs');
  if(jobs.length===0)throw new Error('Empty source response');
  const old=await ops.existingKeys(db,jobs);
  const newJobs=[];
  for(const j of jobs)if(!old.has(j.identity))newJobs.push({
    identity:j.identity,source_id:j.source_id,source_account:j.source_account,
    source_job_id:j.source_job_id,title:j.title,url:j.url,source_url:j.source_url,
    remote:j.remote,location:j.location
  });
  return {cycle,source:gate.source,observations:jobs.length,already_known:old.size,newJobs};
}
async function classify(db,cycle,now){
  const [source,index,radar,poll]=await Promise.all([
    readStage(db,cycle,'source_gate'),
    readStage(db,cycle,'application_history'),
    readStage(db,cycle,'radar_history'),
    readStage(db,cycle,'official_ats')
  ]);
  const officialIndex={known:new Set(index.known),applied:new Set(index.applied)};
  const listed=new Set(radar.listed),urls=new Set(radar.role_keys);
  const candidates=[],out={applied:0,known:0,irrelevant:0,radar_duplicates:0};
  for(const job of poll.newJobs) {
    const prev=matchRegister(job,officialIndex);
    const dup=listed.has(job.identity)||strongRoleKeys(job.url).some(x=>urls.has(x));
    if(prev.applied)out.applied++;
    else if(prev.known)out.known++;
    else if(dup)out.radar_duplicates++;
    else if(!preliminaryInterest(job))out.irrelevant++;
    else if(candidates.length<MAX_CANDIDATES)candidates.push({
      identity:job.identity,source_id:job.source_id,title:job.title,url:job.url
    });
    else throw new Error('Too many source jobs');
  }
  return {version:1,cycle,source:source.source,status:'review_ready',
    screened_at:new Date(now).toISOString(),
    observations:poll.observations,previously_observed:poll.already_known,
    rejected:out,review_count:candidates.length,candidates,
    manual_review_required:true,google_sheet_rows_written:0,application_submissions:0};
}
export async function runStagedReview(env,ops={}){
  // Dual opt-in; setting RADAR_ENABLED alone never starts this pipeline.
  if(env.RADAR_ENABLED!=='1'||env.RADAR_PIPELINE_MODE!=='staged_review'||!env.RADAR_DB)
    return {status:'disabled'};
  if(!env.GOOGLE_SERVICE_ACCOUNT_JSON||!env.VACATURE_REGISTER_ID||!env.RADAR_RESULT_ID)
    return {status:'partial',errors:1,reason:'missing_bindings'};
  const db=env.RADAR_DB,now=ops.now?.()??Date.now();
  let raw=await getMeta(db,STAGE_CONTROL);
  let state=parse(raw);
  // A terminated Free-tier invocation leaves a claimed stage; never rerun it.
  // Purge temporary private snapshots after the deadline instead.
  if(raw?.startsWith('running:')){
    const id=/^running:(cycle_(\d+)_\d+):\d+$/.exec(raw);
    if(!id||now-Number(id[2])<=TTL_MS)return {status:'overlap_skipped',sources:0};
    try{
      await clearSnapshots(db,id[1]);
      await changeControl(db,raw,'failed:'+id[1]+':interrupted');
    }catch{return {status:'partial',errors:1,reason:'stage_cleanup_failed'};}
    return {status:'partial',errors:1,reason:'interrupted_cycle'};
  }
  if(!raw||state?.status==='done'){
    if(raw&&now-Date.parse(state.finished_at||'')<60000)return {status:'cooldown',sources:0};
    const cursor=Number(await getMeta(db,STAGE_CURSOR)||0);
    const next=makeCycle(now,Number.isSafeInteger(cursor)&&cursor>=0?cursor:0);
    const value=JSON.stringify(next);
    if(!raw){
      await db.prepare('INSERT OR IGNORE INTO radar_metadata(name,value) VALUES(?,?)')
        .bind(STAGE_CONTROL,value).run();
    }else{
      try{await changeControl(db,raw,value);}catch{return {status:'overlap_skipped',sources:0};}
    }
    raw=await getMeta(db,STAGE_CONTROL);
    state=parse(raw);
  }
  if(!state||state.version!==1||!Number.isInteger(state.phase)||
      state.phase<0||state.phase>=STAGES.length||
      !/^cycle_\d+_\d+$/.test(state.run||''))
    return {status:'partial',errors:1,reason:'invalid_control'};
  if(now>Date.parse(state.expires_at)||now<Date.parse(state.started_at)-1000){
    try{
      await clearSnapshots(db,state.run);
      await changeControl(db,raw,'failed:'+state.run+':expired');
    }catch{return {status:'partial',errors:1,reason:'stage_cleanup_failed'};}
    return {status:'partial',errors:1,reason:'expired_cycle'};
  }
  const claim='running:'+state.run+':'+state.phase;
  try{await changeControl(db,raw,claim);}catch{return {status:'overlap_skipped',sources:0};}
  const name=STAGES[state.phase];
  let result;
  try {
    if(name==='source_gate')result=await readSourceGate(env,ops,state.run,state.cursor);
    else if(name==='vacancy_history')result=await readVacancyHistory(env,ops,state.run);
    else if(name==='application_history')result=await readApplicationHistory(env,ops,state.run,db);
    else if(name==='radar_history')result=await readRadarHistory(env,ops,state.run);
    else if(name==='official_ats')result=await readOfficialSource(env,ops,state.run,db);
    else if(name==='review_only')result=await classify(db,state.run,now);
    else throw new Error('Invalid stage state');
    if(name==='review_only'){
      await putMeta(db,STAGE_RECEIPT,result);
      await db.prepare('INSERT INTO radar_metadata(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value')
        .bind(STAGE_CURSOR,String(state.cursor+1)).run();
      // Clear temporary private snapshots; retain only the reviewed receipt.
      await clearSnapshots(db,state.run);
    }else await storeStage(db,state.run,name,result);
    const finished=name==='review_only';
    const next=finished?JSON.stringify({
      status:'done',version:1,run:state.run,finished_at:new Date(now).toISOString(),
      source:result.source,review_count:result.review_count
    }):JSON.stringify({...state,phase:state.phase+1});
    await changeControl(db,claim,next);
    return {status:'ok',sources:name==='official_ats'?1:0,
      phase:name,phase_index:state.phase+1,total_phases:STAGES.length,
      review_count:finished?result.review_count:0,new_records:0};
  }catch(error){
    const reason=saneError(error);
    try {
      await clearSnapshots(db,state.run);
      await putMeta(db,'micro:v1:last_failure',{cycle:state.run,phase:name,reason,
        at:new Date(now).toISOString()});
      await changeControl(db,claim,'failed:'+state.run+':'+name);
    }catch {
      // Leave the locked stage in place; never silently retry after partial failures.
    }
    return {status:'partial',sources:0,errors:1,reason};
  }
}
