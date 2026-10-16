// Phase 1 of the Free-tier migration: resumable review-only Cron.
// All business records and Google Sheets are read-only in this pipeline.
// The legacy delivery path is not invoked. Release requires a separate gate.
import {
  PILOT_SOURCES,buildRegisterIndex,canonicalUrl,
  matchRegister,preliminaryInterest,strongRoleKeys
} from './logic.mjs';

export const STAGE_CONTROL='micro:v2:control';
export const STAGE_RECEIPT='micro:v2:receipt';
export const STAGE_CURSOR='micro:v2:cursor';
export const STAGES=Object.freeze([
  'source_gate','vacancy_history','application_rows','event_rows',
  'application_index','radar_history','official_ats','candidate_screen',
  'review_only'
]);
const TTL_MS=12*60*1000;
const PAGED_TTL_MS=135*60*1000; // Long review-only cycle; still no business/Sheet writes.
const VACANCY_PAGE_ROWS=16;
const MAX_VACANCY_ROWS=1536; // Bounded 96 pages; never silently omit history.
const STAGE_LEASE_MS=2*60*1000;
const RETRY_DELAY_MS=60*1000;
const MAX_STAGE_RETRIES=1;
const TRANSIENT_HTTP=/^(?:Sheets read HTTP|Google OAuth HTTP|Public API HTTP) 5\d\d$/;
const MAX_SNAPSHOT_BYTES=210000;
const MAX_JOBS=160;
const MAX_CANDIDATES=160;

function saneError(error) {
  const str=String(error?.message||'');
  if (/^(Source gate header mismatch|Vacature Register header mismatch|Vacancy history size exceeds safe page limit|Application header mismatch|ApplicationEvents header mismatch|Radar header mismatch|No active registered source pair|Official source has no seeded baseline|Unexpected source account|Unexpected source payload|Empty source response|Too many source jobs|Stage snapshot too large|Missing or stale staged snapshot|Invalid stage state|Stage race|Stage data malformed)$/.test(str))
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
function snapshotName(cycle,step){return 'micro:v2:snapshot:'+cycle+':'+step;}
async function clearSnapshots(db,cycle){
  // One indexed D1 delete covers both ordinary and bounded page checkpoints.
  // GLOB treats the underscores in cycle IDs literally, unlike SQL LIKE.
  await db.prepare('DELETE FROM radar_metadata WHERE name GLOB ?')
    .bind('micro:v2:snapshot:'+cycle+':*').run();
}

function makeCycle(now,cursor,ttl=TTL_MS) {
  return {
    version:2,run:'cycle_'+now+'_'+cursor,phase:0,cursor,
    started_at:new Date(now).toISOString(),expires_at:new Date(now+ttl).toISOString()
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

// Write one page and advance its cursor in ONE D1 transaction/subrequest.
// The conditional INSERT prevents orphan pages on a lost CAS. D1 batch()
// is transactional: if its second statement fails, the first is rolled back.
async function advanceHistoryPage(db,cycle,claim,next,page){
  const key=snapshotName(cycle,'vacancy_page_'+page.first);
  const snapshot=JSON.stringify({cycle,data:{rows:page.rows}});
  if(snapshot.length>MAX_SNAPSHOT_BYTES)throw new Error('Stage snapshot too large');
  const result=await db.batch([
    db.prepare('INSERT INTO radar_metadata(name,value) '+
      'SELECT ?,? WHERE EXISTS (SELECT 1 FROM radar_metadata WHERE name=? AND value=?) '+
      'ON CONFLICT(name) DO UPDATE SET value=excluded.value')
      .bind(key,snapshot,STAGE_CONTROL,claim),
    db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')
      .bind(next,STAGE_CONTROL,claim)
  ]);
  if(result?.[0]?.meta?.changes!==1||result?.[1]?.meta?.changes!==1)
    throw new Error('Stage race');
}

async function readSourceGate(env,ops,cycle,cursor){
  const token=await ops.accessToken(env);
  const chunks=await ops.readRanges(env.VACATURE_REGISTER_ID,
    ["'Bronnen'!A1:A","'Bronnen'!M1:M"],token);
  if(chunks.length!==2)throw new Error('Stage data malformed');
  // Only six IDs can authorize a pilot source. Avoid allocating sparse
  // 13-column arrays for the entire Bronnen tab on every cold Cron.
  const ids=chunks[0],statuses=chunks[1];
  if(ids?.[0]?.[0]!=='source_id'||statuses?.[0]?.[0]!=='status')
    throw new Error('Source gate header mismatch');
  const required=new Set(PILOT_SOURCES.flatMap(source=>[
    source.source_id,source.employer_source_id
  ]));
  const states=new Map();
  for(let i=1;i<ids.length;i++){
    const id=ids[i]?.[0];
    if(id&&required.has(id))states.set(id,statuses[i]?.[0]);
  }
  const active=PILOT_SOURCES.filter(source=>
    states.get(source.source_id)==='active'&&
    states.get(source.employer_source_id)==='active');
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
// Separate the expensive Google read and application dedupe into short Cron phases.

/**
 * Bounded, resumable Google Sheet history:
 * - a separate ID-only read establishes the LAST nonempty vacancy-id row;
 * - each later Cron reads at most 16 rows in the two required column pairs;
 * - each page is its own D1 snapshot, never a growing full-history rewrite;
 * - a final D1-only step assembles the same sparse row shape as the legacy path.
 * Empty gaps inside the Sheet are retained; entries after the last nonempty ID
 * cannot contribute to buildRegisterIndex, so they are not silently omitted.
 * This is review-only: any error blocks candidate finalization.
 */
async function readVacancyHistoryPaged(env,ops,cycle,state,db){
  if(state.history_end===undefined){
    const token=await ops.accessToken(env);
    const parts=await ops.readRanges(env.VACATURE_REGISTER_ID,["'Vacatures'!A1:A"],token);
    if(parts.length!==1||parts[0]?.[0]?.[0]!=='vacancy_id')
      throw new Error('Vacature Register header mismatch');
    const end=parts[0].length;
    if(end<1||end>MAX_VACANCY_ROWS)throw new Error('Vacancy history size exceeds safe page limit');
    return {kind:'progress',next:{history_end:end,history_next:1}};
  }
  const last=state.history_end,first=state.history_next;
  if(!Number.isSafeInteger(last)||last<1||last>MAX_VACANCY_ROWS||
     !Number.isSafeInteger(first)||first<1||first>last+1)
    throw new Error('Invalid stage state');
  if(first<=last){
    const end=Math.min(last,first+VACANCY_PAGE_ROWS-1);
    const token=await ops.accessToken(env);
    const parts=await ops.readRanges(env.VACATURE_REGISTER_ID,[
      "'Vacatures'!A"+first+":B"+end,
      "'Vacatures'!G"+first+":H"+end
    ],token);
    if(parts.length!==2)throw new Error('Stage data malformed');
    const rows=mergeColumns(parts,[[0,0,2],[1,6,2]]);
    if(first===1)headers(rows,[[0,'vacancy_id'],[1,'status'],[6,'canonical_url'],[7,'official_url']],
      'Vacature Register header mismatch');
    // Sheets trims trailing empty rows of each requested range. Preserve
    // their absolute positions, including gaps preceding later IDs.
    while(rows.length<end-first+1)rows.push([]);
    if(rows.length!==end-first+1)throw new Error('Stage data malformed');
    return {kind:'progress',next:{history_next:end+1},page:{first,rows}};
  }
  // The last pass performs no Google OAuth or network fetch.
  // Snapshots remain private and are purged at finalization/failure.
  const starts=[],keys=[];
  for(let row=1;row<=last;row+=VACANCY_PAGE_ROWS){
    starts.push(row);
    keys.push(snapshotName(cycle,'vacancy_page_'+row));
  }
  // D1 Free allows only 50 subrequests per Worker invocation. Reading 48
  // pages individually, plus the control claim and checkpoint mutations,
  // could exceed that budget. Fetch exact page keys in one indexed SELECT.
  const result=await db.prepare('SELECT name,value FROM radar_metadata WHERE name IN ('+
    keys.map(()=>'?').join(',')+')').bind(...keys).all();
  if(result.results?.length!==keys.length)throw new Error('Missing or stale staged snapshot');
  const byName=new Map(result.results.map(row=>[row.name,row.value]));
  if(byName.size!==keys.length)throw new Error('Stage data malformed');
  const rows=[];
  for(let i=0;i<keys.length;i++){
    const data=stateSnapshot(byName.get(keys[i]),cycle);
    const count=Math.min(VACANCY_PAGE_ROWS,last-starts[i]+1);
    if(!Array.isArray(data.rows)||data.rows.length!==count)
      throw new Error('Stage data malformed');
    rows.push(...data.rows);
  }
  if(rows.length!==last)throw new Error('Stage data malformed');
  headers(rows,[[0,'vacancy_id'],[1,'status'],[6,'canonical_url'],[7,'official_url']],
    'Vacature Register header mismatch');
  return {cycle,rows,read_at:new Date().toISOString()};
}

async function readApplicationRows(env,ops,cycle){
  const token=await ops.accessToken(env);
  const chunks=await ops.readRanges(env.VACATURE_REGISTER_ID,[
    "'Applications'!A1:A","'Applications'!C1:C","'Applications'!E1:E"
  ],token);
  if(chunks.length!==3)throw new Error('Stage data malformed');
  const rows=mergeColumns(chunks,[[0,0,1],[1,2,1],[2,4,1]]);
  headers(rows,[[0,'vacancy_id'],[2,'status'],[4,'application_url']],'Application header mismatch');
  return {cycle,rows,read_at:new Date().toISOString()};
}
async function readEventRows(env,ops,cycle){
  const token=await ops.accessToken(env);
  const chunks=await ops.readRanges(env.VACATURE_REGISTER_ID,[
    "'ApplicationEvents'!A1:B","'ApplicationEvents'!D1:D","'ApplicationEvents'!F1:F"
  ],token);
  if(chunks.length!==3)throw new Error('Stage data malformed');
  const rows=mergeColumns(chunks,[[0,0,2],[1,3,1],[2,5,1]]);
  headers(rows,[[0,'event_id'],[1,'vacancy_id'],[3,'event_type'],[5,'status_after']],
    'ApplicationEvents header mismatch');
  return {cycle,rows,read_at:new Date().toISOString()};
}
async function buildApplicationIndex(db,cycle){
  const [vacancy,application,events]=await Promise.all([
    readStage(db,cycle,'vacancy_history'),
    readStage(db,cycle,'application_rows'),
    readStage(db,cycle,'event_rows')
  ]);
  const index=buildRegisterIndex(vacancy.rows,application.rows,events.rows);
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
  // A partly populated Radar row can contain an official URL without
  // an observation key. It must still suppress an already-seen role.
  for(let i=1;i<Math.max(chunks[0].length,chunks[1].length);i++){
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
async function screenCandidates(db,cycle,now){
  const [source,index,radar,poll]=await Promise.all([
    readStage(db,cycle,'source_gate'),
    readStage(db,cycle,'application_index'),
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
  return {version:2,cycle,source:source.source,status:'review_ready',
    screened_at:new Date(now).toISOString(),
    observations:poll.observations,previously_observed:poll.already_known,
    rejected:out,review_count:candidates.length,candidates,
    manual_review_required:true,google_sheet_rows_written:0,application_submissions:0};
}
async function finalizeReview(db,cycle){
  const receipt=await readStage(db,cycle,'candidate_screen');
  if(receipt.cycle!==cycle||receipt.status!=='review_ready'||
    receipt.manual_review_required!==true||
    receipt.google_sheet_rows_written!==0||receipt.application_submissions!==0)
    throw new Error('Stage data malformed');
  return receipt;
}
export async function runStagedReview(env,ops={}){
  // Dual opt-in; setting RADAR_ENABLED alone never starts this pipeline.
  if(env.RADAR_ENABLED!=='1'||env.RADAR_PIPELINE_MODE!=='staged_review'||!env.RADAR_DB)
    return {status:'disabled'};
  if(!env.GOOGLE_SERVICE_ACCOUNT_JSON||!env.VACATURE_REGISTER_ID||!env.RADAR_RESULT_ID)
    return {status:'partial',errors:1,reason:'missing_bindings'};
  const db=env.RADAR_DB,now=ops.now?.()??Date.now();
  const cycleTtl=ops.pagedVacancy===true?PAGED_TTL_MS:TTL_MS;
  let raw=await getMeta(db,STAGE_CONTROL);
  let state=parse(raw);
  // A claimed stage has a two-minute lease. Recover completed snapshots,
  // otherwise retry at most once; never overlap running invocations.
  if(raw?.startsWith('running:')){
    const claim=/^running:(cycle_(\d+)_(\d+)):(\d+):(\d+):(\d+)(?::(\d+):(\d+))?$/.exec(raw);
    if(!claim){
      // Old-format claims have no lease timestamp and remain fail-closed.
      const old=/^running:(cycle_(\d+)_\d+):\d+$/.exec(raw);
      if(!old||now-Number(old[2])<=cycleTtl)return {status:'overlap_skipped',sources:0};
      try{
        await clearSnapshots(db,old[1]);
        await changeControl(db,raw,'failed:'+old[1]+':interrupted');
      }catch{return {status:'partial',errors:1,reason:'stage_cleanup_failed'};}
      return {status:'partial',errors:1,reason:'interrupted_cycle'};
    }
    const run=claim[1],started=Number(claim[2]),cursor=Number(claim[3]);
    const phase=Number(claim[4]),claimedAt=Number(claim[5]),attempt=Number(claim[6]);
    const historyEnd=claim[7]===undefined?undefined:Number(claim[7]);
    const historyNext=claim[8]===undefined?undefined:Number(claim[8]);
    if(![started,cursor,phase,claimedAt,attempt].every(Number.isSafeInteger)||
       phase>=STAGES.length||attempt>MAX_STAGE_RETRIES||claimedAt<started||
       now<claimedAt||
       (historyEnd!==undefined&&(
         phase!==STAGES.indexOf('vacancy_history')||
         !Number.isSafeInteger(historyEnd)||historyEnd<1||historyEnd>MAX_VACANCY_ROWS||
         !Number.isSafeInteger(historyNext)||historyNext<1||historyNext>historyEnd+1)))
      return {status:'partial',errors:1,reason:'invalid_control'};
    const progress=historyEnd===undefined?{}:{
      history_end:historyEnd,history_next:historyNext
    };
    if(now-claimedAt<STAGE_LEASE_MS)return {status:'overlap_skipped',sources:0};
    try{
      if(now-started>cycleTtl){
        await clearSnapshots(db,run);
        await changeControl(db,raw,'failed:'+run+':expired');
        return {status:'partial',errors:1,reason:'expired_cycle'};
      }
      const phaseName=STAGES[phase];
      if(phaseName==='review_only'){
        const receipt=parse(await getMeta(db,STAGE_RECEIPT));
        if(receipt?.cycle===run&&receipt.status==='review_ready'&&
           receipt.manual_review_required===true&&
           receipt.google_sheet_rows_written===0&&receipt.application_submissions===0){
          // Idempotently finish an already persisted review receipt.
          await db.prepare('INSERT INTO radar_metadata(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value')
            .bind(STAGE_CURSOR,String(cursor+1)).run();
          await clearSnapshots(db,run);
          await changeControl(db,raw,JSON.stringify({
            status:'done',version:2,run,finished_at:new Date(now).toISOString(),
            source:receipt.source,review_count:receipt.review_count
          }));
          return {status:'recovered_completed',sources:0,phase:phaseName};
        }
      }else{
        const snapshot=parse(await getMeta(db,snapshotName(run,phaseName)));
        if(snapshot?.cycle===run&&snapshot.data){
          // A crash after writing the final stage checkpoint must not
          // execute the stage twice (or perform a second source fetch).
          await changeControl(db,raw,JSON.stringify({
            ...makeCycle(started,cursor,cycleTtl),phase:phase+1,attempts:0
          }));
          return {status:'recovered_checkpoint',sources:0,phase:phaseName};
        }
        if(phaseName==='vacancy_history'&&historyEnd!==undefined&&
           historyNext<=historyEnd){
          // Paged stages persist a named page BEFORE updating control.
          // A failed compare-and-swap must not force a reread of that page.
          const saved=parse(await getMeta(db,snapshotName(run,
            'vacancy_page_'+historyNext)));
          const count=Math.min(VACANCY_PAGE_ROWS,historyEnd-historyNext+1);
          if(saved?.cycle===run&&Array.isArray(saved.data?.rows)&&
             saved.data.rows.length===count){
            await changeControl(db,raw,JSON.stringify({
              ...makeCycle(started,cursor,cycleTtl),phase,attempts:0,
              history_end:historyEnd,history_next:historyNext+count
            }));
            return {status:'recovered_checkpoint',sources:0,phase:phaseName};
          }
        }
      }
      if(attempt<MAX_STAGE_RETRIES){
        await changeControl(db,raw,JSON.stringify({
          ...makeCycle(started,cursor,cycleTtl),phase,attempts:attempt+1,
          ...progress
        }));
        return {status:'recovered_retry',sources:0,phase:phaseName};
      }
      await clearSnapshots(db,run);
      await putMeta(db,'micro:v2:last_failure',{cycle:run,phase:phaseName,
        reason:'interrupted_stage',at:new Date(now).toISOString()});
      await changeControl(db,raw,'failed:'+run+':interrupted');
      return {status:'partial',errors:1,reason:'interrupted_cycle'};
    }catch{return {status:'partial',errors:1,reason:'stage_cleanup_failed'};}
  }
  if(raw?.startsWith('failed:'))return {status:'halted',sources:0};
  if(ops.singleCycle===true&&state?.status==='done')return {status:'canary_complete',sources:0};
  if(!raw||state?.status==='done'){
    if(raw&&now-Date.parse(state.finished_at||'')<60000)return {status:'cooldown',sources:0};
    const cursor=Number(await getMeta(db,STAGE_CURSOR)||0);
    const next=makeCycle(now,Number.isSafeInteger(cursor)&&cursor>=0?cursor:0,cycleTtl);
    const value=JSON.stringify(next);
    if(!raw){
      const claim=await db.prepare('INSERT OR IGNORE INTO radar_metadata(name,value) VALUES(?,?)')
        .bind(STAGE_CONTROL,value).run();
      if(claim.meta?.changes===1){
        // This invocation created the cycle. Reading it back costs an
        // unnecessary D1 round trip on the CPU-critical first phase.
        raw=value;
        state=next;
      }else{
        // Another invocation already established control. It may have
        // claimed or advanced the stage while we were awaiting D1.
        // Defer to the next Cron instead of racing the winner.
        return {status:'overlap_skipped',sources:0};
      }
    }else{
      try{await changeControl(db,raw,value);}catch{return {status:'overlap_skipped',sources:0};}
      raw=value;
      state=next;
    }
    if(ops.splitBootstrap===true){
      // The first Free Cron in a new review cycle only establishes D1
      // control. Source Google OAuth and policy checks start next minute,
      // with no extra scheduler, secret storage, or relaxed source policy.
      return {status:'initialized',phase:'cycle_bootstrap',sources:0,
        phase_index:0,total_phases:STAGES.length,new_records:0};
    }
  }
  if(!state||state.version!==2||!Number.isInteger(state.phase)||
      state.phase<0||state.phase>=STAGES.length||
      !/^cycle_\d+_\d+$/.test(state.run||'')||
      !Number.isSafeInteger(state.attempts??0)||
      (state.attempts??0)<0||(state.attempts??0)>MAX_STAGE_RETRIES)
    return {status:'partial',errors:1,reason:'invalid_control'};
  if(state.retry_after!==undefined&&!Number.isSafeInteger(state.retry_after))
    return {status:'partial',errors:1,reason:'invalid_control'};
  if(now>Date.parse(state.expires_at)||now<Date.parse(state.started_at)-1000){
    try{
      await clearSnapshots(db,state.run);
      await changeControl(db,raw,'failed:'+state.run+':expired');
    }catch{return {status:'partial',errors:1,reason:'stage_cleanup_failed'};}
    return {status:'partial',errors:1,reason:'expired_cycle'};
  }
  if(state.retry_after&&now<state.retry_after)
    return {status:'retry_wait',sources:0};
  const progress=(state.phase===STAGES.indexOf('vacancy_history')&&
    state.history_end!==undefined&&state.history_next!==undefined)
    ?':'+state.history_end+':'+state.history_next:'';
  const claim='running:'+state.run+':'+state.phase+':'+now+':'+
    (state.attempts||0)+progress;
  try{await changeControl(db,raw,claim);}catch{return {status:'overlap_skipped',sources:0};}
  const name=STAGES[state.phase];
  let result;
  try {
    if(name==='source_gate')result=await readSourceGate(env,ops,state.run,state.cursor);
    else if(name==='vacancy_history')result=ops.pagedVacancy===true
      ?await readVacancyHistoryPaged(env,ops,state.run,state,db)
      :await readVacancyHistory(env,ops,state.run);
    else if(name==='application_rows')result=await readApplicationRows(env,ops,state.run);
    else if(name==='event_rows')result=await readEventRows(env,ops,state.run);
    else if(name==='application_index')result=await buildApplicationIndex(db,state.run);
    else if(name==='radar_history')result=await readRadarHistory(env,ops,state.run);
    else if(name==='official_ats')result=await readOfficialSource(env,ops,state.run,db);
    else if(name==='candidate_screen')result=await screenCandidates(db,state.run,now);
    else if(name==='review_only')result=await finalizeReview(db,state.run);
    else throw new Error('Invalid stage state');
    if(name==='vacancy_history'&&result?.kind==='progress'){
      const advanced=JSON.stringify({
        ...state,...result.next,attempts:0,retry_after:undefined
      });
      if(result.page)await advanceHistoryPage(db,state.run,claim,advanced,result.page);
      else await changeControl(db,claim,advanced);
      return {status:'checkpointed',sources:0,phase:name,
        phase_index:state.phase+1,total_phases:STAGES.length,new_records:0};
    }
    if(name==='review_only'){
      await putMeta(db,STAGE_RECEIPT,result);
      await db.prepare('INSERT INTO radar_metadata(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value')
        .bind(STAGE_CURSOR,String(state.cursor+1)).run();
      // Clear temporary private snapshots; retain only the reviewed receipt.
      await clearSnapshots(db,state.run);
    }else await storeStage(db,state.run,name,result);
    const finished=name==='review_only';
    const next=finished?JSON.stringify({
      status:'done',version:2,run:state.run,finished_at:new Date(now).toISOString(),
      source:result.source,review_count:result.review_count
    }):JSON.stringify({...state,phase:state.phase+1,attempts:0,retry_after:undefined});
    await changeControl(db,claim,next);
    return {status:'ok',sources:name==='official_ats'?1:0,
      phase:name,phase_index:state.phase+1,total_phases:STAGES.length,
      review_count:finished?result.review_count:0,new_records:0};
  }catch(error){
    const reason=saneError(error);
    try {
      await putMeta(db,'micro:v2:last_failure',{cycle:state.run,phase:name,reason,
        at:new Date(now).toISOString()});
      // Only transient 5xx responses receive one delayed retry. 429, policy
      // violations, invalid data and unknown errors halt immediately.
      if(TRANSIENT_HTTP.test(reason)&&(state.attempts||0)<MAX_STAGE_RETRIES&&
         now+RETRY_DELAY_MS<Date.parse(state.expires_at)){
        await changeControl(db,claim,JSON.stringify({
          ...state,attempts:(state.attempts||0)+1,retry_after:now+RETRY_DELAY_MS
        }));
        return {status:'retry_scheduled',sources:0,errors:1,reason};
      }
      await clearSnapshots(db,state.run);
      await changeControl(db,claim,'failed:'+state.run+':'+name);
    }catch {
      // Leave the claim in place for bounded lease recovery, never unlimited retries.
    }
    return {status:'partial',sources:0,errors:1,reason};
  }
}
