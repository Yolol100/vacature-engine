// Node.js review-only successor to the Cloudflare poll. NO external writes.
import {PILOT_SOURCES,buildRegisterIndex,matchRegister,preliminaryInterest,strongRoleKeys,canonicalUrl,isValidJob} from './logic.mjs';
import {safeDiagnosticError} from './health.mjs';
import {parseReviewState} from './review-state.mjs';
export const MAX_REVIEW=10;
// One bounded 5xx retry for a public ATS source. Never retry a 429 immediately,
// authentication failures, invalid payloads, policy changes or unknown errors.
export async function pollWithRetry(source,publicJobs,wait=ms=>new Promise(resolve=>setTimeout(resolve,ms))){
  try{return await publicJobs(source);}
  catch(error){
    const status=Number(error?.status)||
      Number(/^Public API HTTP (5\d\d)$/.exec(String(error?.message||''))?.[1]);
    if(!Number.isSafeInteger(status)||status<500||status>599||
       (Number.isFinite(error?.retryAfterSeconds)&&error.retryAfterSeconds>3))
      throw error;
    await wait(300);
    return publicJobs(source);
  }
}
const REGISTER=[
  ["'Config'!A1:B"],
  ["'Bronnen'!A1:A","'Bronnen'!M1:M"],
  ["'Vacatures'!A1:B","'Vacatures'!G1:H"],
  ["'Applications'!A1:A","'Applications'!C1:C","'Applications'!E1:E"],
  ["'ApplicationEvents'!A1:B","'ApplicationEvents'!D1:D","'ApplicationEvents'!F1:F"]
];
const RADAR=[
  ["'Nieuwe vacatures'!A1:A","'Nieuwe vacatures'!F1:F"],
  ["'Radar State'!A1:A","'Radar State'!C1:C","'Radar State'!D1:D"]
];
function header(parts,expect) {
  if(parts.length!==expect.length||expect.some((name,i)=>parts[i]?.[0]?.[0]!==name))
    throw new Error('Spreadsheet header mismatch: stop before dedupe or writes');
}
function expand(parts,specs) {
  const count=Math.max(0,...parts.map(p=>p.length)),rows=[];
  for(let i=0;i<count;i++){
    const row=[];
    specs.forEach(([offset,width],n)=>{
      const source=parts[n][i]||[];
      for(let c=0;c<width;c++)if(source[c]!==undefined)row[offset+c]=source[c];
    });
    rows.push(row);
  }
  return rows;
}
function uniqueIdentity(rows,keyCol,urlCol) {
  const ids=new Set(),roles=new Set();
  for(const row of rows.slice(1)) {
    const key=String(row[keyCol]||'').trim();
    if(key) {
      if(ids.has(key))throw new Error('Duplicate identity in Radar history');
      ids.add(key);
    }
    for(const identity of strongRoleKeys(canonicalUrl(row[urlCol]||'')))roles.add(identity);
  }
  return {ids,roles};
}
export async function reviewOnce({env,accessToken,readRanges,publicJobs,maxCandidates=5,priorState}) {
  const reviewHistory=parseReviewState(priorState);
  if(!Number.isInteger(maxCandidates)||maxCandidates<1||maxCandidates>MAX_REVIEW)
    throw new Error('Invalid candidate limit');
  if(!env.GOOGLE_SERVICE_ACCOUNT_JSON||!env.VACATURE_REGISTER_ID||!env.RADAR_RESULT_ID)
    throw new Error('Missing required bindings or secrets');
  const token=await accessToken(env);
  // Google batchGet supports all ranges for one spreadsheet. Read the two
  // spreadsheet IDs independently so a 403 identifies the failed permission
  // boundary. Never poll ATS when either historical data source is unavailable.
  async function readGroups(id,groups){
    const flat=groups.flat();
    const values=await readRanges(id,flat,token);
    if(!Array.isArray(values)||values.length!==flat.length)
      throw new Error('Sheets response incomplete');
    let offset=0;
    return groups.map(group=>{
      const out=values.slice(offset,offset+group.length);
      offset+=group.length;
      return out;
    });
  }
  const attempts=await Promise.allSettled([
    readGroups(env.VACATURE_REGISTER_ID,REGISTER),
    readGroups(env.RADAR_RESULT_ID,RADAR)
  ]);
  if(attempts.some(x=>x.status==='rejected')){
    const describe=attempt=>{
      if(attempt.status==='fulfilled')return 'OK';
      const err=attempt.reason;
      const status=Number(err?.httpStatus)||
        Number(/^Sheets read HTTP ([45]\\d\\d)$/.exec(String(err?.message||''))?.[1]);
      const reason=String(err?.sheetReason||'UNCLASSIFIED');
      const allowed=['PERMISSION_DENIED','UNAUTHENTICATED','RESOURCE_EXHAUSTED',
        'NOT_FOUND','ACCESS_TOKEN_SCOPE_INSUFFICIENT','insufficientPermissions',
        'rateLimitExceeded','accessNotConfigured','forbidden','UNCLASSIFIED'];
      return (Number.isSafeInteger(status)&&status>=400&&status<=599?
        'HTTP'+status:'FAILED')+':'+(allowed.includes(reason)?reason:'UNCLASSIFIED');
    };
    throw new Error('Radar Sheets preflight failed register='+describe(attempts[0])+
      ' radar='+describe(attempts[1]));
  }
  const chunks=[...attempts[0].value,...attempts[1].value];
  header(chunks[0],['key']);
  if(chunks[0][0]?.[0]?.[1]!=='value')
    throw new Error('Spreadsheet header mismatch: stop before dedupe or writes');
  const config=new Map(chunks[0][0].slice(1).map(x=>[x[0],x[1]]));
  if(String(config.get('radar_enabled')).toUpperCase()!=='FALSE'||
     config.get('radar_delivery')!=='none'||
     config.get('radar_state_branch')!=='radar-state')
    throw new Error('Radar is not in a read-only transition state');
  header(chunks[1],['source_id','status']);
  header(chunks[2],['vacancy_id','canonical_url']);
  if(chunks[2][0][0][1]!=='status'||chunks[2][1][0][1]!=='official_url')
    throw new Error('Spreadsheet header mismatch: stop before dedupe or writes');
  header(chunks[3],['vacancy_id','status','application_url']);
  header(chunks[4],['event_id','event_type','status_after']);
  if(chunks[4][0]?.[0]?.[1]!=='vacancy_id')
    throw new Error('Spreadsheet header mismatch: stop before dedupe or writes');
  header(chunks[5],['observation_key','officiele_url']);
  header(chunks[6],['identity','official_url','status']);
  const sourceRows=expand(chunks[1],[[0,1],[12,1]]);
  const vacancyRows=expand(chunks[2],[[0,2],[6,2]]);
  const applicationRows=expand(chunks[3],[[0,1],[2,1],[4,1]]);
  const eventRows=expand(chunks[4],[[0,2],[3,1],[5,1]]);
  const active=new Map();
  for(const row of sourceRows.slice(1)) {
    const id=String(row[0]||'').trim();
    if(!id)continue;
    if(active.has(id))throw new Error('Duplicate source ID in live register');
    active.set(id,row[12]);
  }
  const enabled=PILOT_SOURCES.filter(x=>active.get(x.source_id)==='active'&&
    active.get(x.employer_source_id)==='active');
  if(enabled.length===0)throw new Error('No active registered source pair');
  const register=buildRegisterIndex(vacancyRows,applicationRows,eventRows);
  const previous=uniqueIdentity(expand(chunks[5],[[0,1],[5,1]]),0,5);
  const baselineRows=expand(chunks[6],[[0,1],[2,1],[3,1]]);
  const baseline=uniqueIdentity(baselineRows,0,2);
  for(const row of baselineRows.slice(1)){
    const identity=String(row[0]||'').trim();
    if(!identity)continue;
    const parts=identity.split(':');
    const url=canonicalUrl(row[2]||'');
    if(parts.length!==3||row[3]!=='baseline'||
       !isValidJob({identity,source_id:parts[0],
         source_account:parts[1],source_job_id:parts[2],
         title:'historical baseline',url}))
      throw new Error('Radar State baseline unavailable');
  }
  const baselineMinimum=Number(env.RADAR_BASELINE_MIN_RECORDS||26);
  if(!Number.isSafeInteger(baselineMinimum)||baselineMinimum<1||baseline.ids.size<baselineMinimum)
    throw new Error('Radar State baseline unavailable');
  const seenIds=new Set([...previous.ids,...baseline.ids,
    ...reviewHistory.observed.map(v=>v.identity)]);
  const seenRoles=new Set([...previous.roles,...baseline.roles,
    ...reviewHistory.observed.flatMap(v=>strongRoleKeys(v.official_url))]);
  const candidates=[],failures=[];
  const counts={observed:0,previously_seen:0,already_in_register:0,previously_applied:0,
    unrelated:0,review_candidates:0};
  for(const source of enabled) {
    let jobs;
    try {
      jobs=await pollWithRetry(source,publicJobs);
      if(!Array.isArray(jobs)||jobs.length>160)throw new Error('Unexpected public jobs payload');
    }catch(error) {
      failures.push({source:source.source_id+':'+source.account,reason:safeDiagnosticError(error)});
      continue;
    }
    counts.observed+=jobs.length;
    for(const job of jobs) {
      if(job.identity!==[source.source_id,source.account,job.source_job_id].join(':')||
         job.source_id!==source.source_id||job.source_account!==source.account||
         !isValidJob(job)) {
        failures.push({source:source.source_id+':'+source.account,reason:'Unexpected ATS job host: source contract changed'});
        continue;
      }
      const match=matchRegister(job,register);
      const roleKeys=strongRoleKeys(job.url);
      const duplicate=seenIds.has(job.identity)||roleKeys.some(k=>seenRoles.has(k));
      if(match.applied)counts.previously_applied++;
      else if(match.known)counts.already_in_register++;
      else if(duplicate)counts.previously_seen++;
      else if(!preliminaryInterest(job))counts.unrelated++;
      else {
        for(const k of roleKeys)seenRoles.add(k);
        seenIds.add(job.identity);
        if(candidates.length<maxCandidates)candidates.push({
          observation_key:job.identity,source_id:job.source_id,employer:source.employer,
          title:String(job.title).slice(0,240),official_url:job.url,
          location:String(job.location||'').slice(0,160),remote_text:String(job.remote||'').slice(0,160),
          verification:'official_ats_observed; manual authenticity, remote/NL eligibility and fit review required'
        });
      }
    }
  }
  counts.review_candidates=candidates.length;
  return {schema_version:1,status:failures.length?'partial':'review_ready',
    mode:'read_only',manual_review_required:true,register_authoritative:true,
    baseline_records_read:baseline.ids.size,
    durable_review_observations:reviewHistory.observed.length,
    google_sheet_rows_written:0,application_submissions:0,
    active_sources:enabled.length,counts,candidates,failures};
}
