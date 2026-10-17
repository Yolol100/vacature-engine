// Node.js review-only successor to the Cloudflare poll. NO external writes.
import {PILOT_SOURCES,buildRegisterIndex,matchRegister,preliminaryInterest,strongRoleKeys,canonicalUrl,isValidJob} from './logic.mjs';
import {safeDiagnosticError} from './health.mjs';
export const MAX_REVIEW=10;
const REGISTER=[
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
export async function reviewOnce({env,accessToken,readRanges,publicJobs,maxCandidates=5}) {
  if(!Number.isInteger(maxCandidates)||maxCandidates<1||maxCandidates>MAX_REVIEW)
    throw new Error('Invalid candidate limit');
  if(!env.GOOGLE_SERVICE_ACCOUNT_JSON||!env.VACATURE_REGISTER_ID||!env.RADAR_RESULT_ID)
    throw new Error('Missing required bindings or secrets');
  const token=await accessToken(env);
  const chunks=await Promise.all([
    ...REGISTER.map(r=>readRanges(env.VACATURE_REGISTER_ID,r,token)),
    ...RADAR.map(r=>readRanges(env.RADAR_RESULT_ID,r,token))
  ]);
  header(chunks[0],['source_id','status']);
  header(chunks[1],['vacancy_id','canonical_url']);
  if(chunks[1][0][0][1]!=='status'||chunks[1][1][0][1]!=='official_url')
    throw new Error('Spreadsheet header mismatch: stop before dedupe or writes');
  header(chunks[2],['vacancy_id','status','application_url']);
  header(chunks[3],['event_id','event_type','status_after']);
  if(chunks[3][0]?.[0]?.[1]!=='vacancy_id')
    throw new Error('Spreadsheet header mismatch: stop before dedupe or writes');
  header(chunks[4],['observation_key','officiele_url']);
  header(chunks[5],['identity','official_url','status']);
  const sourceRows=expand(chunks[0],[[0,1],[12,1]]);
  const vacancyRows=expand(chunks[1],[[0,2],[6,2]]);
  const applicationRows=expand(chunks[2],[[0,1],[2,1],[4,1]]);
  const eventRows=expand(chunks[3],[[0,2],[3,1],[5,1]]);
  const active=new Map(sourceRows.slice(1).map(x=>[x[0],x[12]]));
  const enabled=PILOT_SOURCES.filter(x=>active.get(x.source_id)==='active'&&
    active.get(x.employer_source_id)==='active');
  if(enabled.length===0)throw new Error('No active registered source pair');
  const register=buildRegisterIndex(vacancyRows,applicationRows,eventRows);
  const previous=uniqueIdentity(expand(chunks[4],[[0,1],[5,1]]),0,5);
  const baseline=uniqueIdentity(expand(chunks[5],[[0,1],[2,1],[3,1]]),0,2);
  if(baseline.ids.size===0)throw new Error('Radar State baseline unavailable');
  const seenIds=new Set([...previous.ids,...baseline.ids]);
  const seenRoles=new Set([...previous.roles,...baseline.roles]);
  const candidates=[],failures=[];
  const counts={observed:0,previously_seen:0,already_in_register:0,previously_applied:0,
    unrelated:0,review_candidates:0};
  for(const source of enabled) {
    let jobs;
    try {
      jobs=await publicJobs(source);
      if(!Array.isArray(jobs)||jobs.length>160)throw new Error('Unexpected public jobs payload');
    }catch(error) {
      failures.push({source:source.source_id+':'+source.account,reason:safeDiagnosticError(error)});
      continue;
    }
    counts.observed+=jobs.length;
    for(const job of jobs) {
      if(!isValidJob(job)) {
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
          title:job.title,official_url:job.url,location:job.location,remote_text:job.remote,
          verification:'official_ats_observed; manual authenticity, remote/NL eligibility and fit review required'
        });
      }
    }
  }
  counts.review_candidates=candidates.length;
  return {schema_version:1,status:failures.length?'partial':'review_ready',
    mode:'read_only',manual_review_required:true,register_authoritative:true,
    baseline_records_read:baseline.ids.size,google_sheet_rows_written:0,application_submissions:0,
    active_sources:enabled.length,counts,candidates,failures};
}
