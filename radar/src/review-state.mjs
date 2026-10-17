// Technical review receipts, kept exclusively on the existing radar-state branch.
// Live Vacature Register is authoritative for policy and application states.
// Never store applicant details, credentials, CV material or applied status here.
import {createHash} from 'node:crypto';
import {canonicalUrl,strongRoleKeys,isValidJob} from './logic.mjs';

export const REVIEW_STATE_VERSION=1;
export const MAX_REVIEW_STATE_ITEMS=5000;
export const MAX_RUN_RECEIPTS=1500;
const EMPTY=Object.freeze({schema_version:1,observed:[],runs:[]});
const ID=/^(?:greenhouse|lever|ashby|personio|workable):[a-z0-9_-]+:[a-zA-Z0-9_-]{1,120}$/;

function object(value) {
  return value!==null&&typeof value==='object'&&!Array.isArray(value);
}
function validObservation(v) {
  if(!object(v)||typeof v.identity!=='string'||!ID.test(v.identity)||
     typeof v.official_url!=='string'||typeof v.title!=='string'||
     typeof v.first_seen_utc!=='string')return false;
  const url=canonicalUrl(v.official_url);
  const [source_id,source_account,source_job_id]=v.identity.split(':');
  if(!isValidJob({...v,url,source_id,source_account,source_job_id})||
     !url||url!==v.official_url||!strongRoleKeys(url).length||
     v.title.length===0||v.title.length>240||
     !Number.isFinite(Date.parse(v.first_seen_utc)))return false;
  const keys=new Set(['identity','official_url','title','first_seen_utc']);
  return Object.keys(v).every(k=>keys.has(k));
}
function validRun(v) {
  if(!object(v)||typeof v.run_id!=='string'||!/^[0-9]{1,24}$/.test(v.run_id)||
     typeof v.digest!=='string'||!/^[a-f0-9]{64}$/.test(v.digest)||
     typeof v.completed_utc!=='string'||!Number.isFinite(Date.parse(v.completed_utc))||
     !Number.isSafeInteger(v.count)||v.count<0||v.count>10)return false;
  return Object.keys(v).every(k=>['run_id','digest','completed_utc','count'].includes(k));
}
export function parseReviewState(input) {
  const data=(input===undefined||input===null||input==='')?EMPTY:
    (typeof input==='string'?JSON.parse(input):input);
  if(!object(data)||data.schema_version!==REVIEW_STATE_VERSION||
     !Array.isArray(data.observed)||!Array.isArray(data.runs)||
     data.observed.length>MAX_REVIEW_STATE_ITEMS||
     data.runs.length>MAX_RUN_RECEIPTS||
     Object.keys(data).some(k=>!['schema_version','observed','runs'].includes(k)))
    throw new Error('Invalid radar review state');
  const ids=new Set(),urls=new Set(),runIds=new Set();
  for(const item of data.observed){
    if(!validObservation(item)||ids.has(item.identity))
      throw new Error('Invalid or duplicate review observation');
    ids.add(item.identity);
    for(const key of strongRoleKeys(item.official_url)){
      if(urls.has(key))throw new Error('Duplicate review official URL');
      urls.add(key);
    }
  }
  for(const receipt of data.runs){
    if(!validRun(receipt)||runIds.has(receipt.run_id))
      throw new Error('Invalid or duplicate review receipt');
    runIds.add(receipt.run_id);
  }
  return {schema_version:1,observed:data.observed.map(x=>({...x})),
    runs:data.runs.map(x=>({...x}))};
}
export function receiptDigest(result) {
  if(!object(result)||result.status!=='review_ready'||result.mode!=='read_only'||
    result.manual_review_required!==true||result.google_sheet_rows_written!==0||
    result.application_submissions!==0||!Array.isArray(result.candidates)||
    result.candidates.length>10||!Array.isArray(result.failures)||
    result.failures.length!==0)
    throw new Error('Unsafe or partial radar result: do not checkpoint');
  // Order-independent input digest for replay checks; only public technical data.
  const simple=result.candidates.map(c=>({
    identity:c.observation_key,url:canonicalUrl(c.official_url),
    title:c.title
  })).sort((a,b)=>a.identity.localeCompare(b.identity));
  if(simple.some(c=>{
    if(!ID.test(c.identity)||!c.url||!c.title||c.title.length>240)return true;
    const [source_id,source_account,source_job_id]=c.identity.split(':');
    return !isValidJob({identity:c.identity,source_id,source_account,
      source_job_id,title:c.title,url:c.url});
  }))
    throw new Error('Invalid radar review candidate');
  return createHash('sha256').update(JSON.stringify(simple)).digest('hex');
}
export function commitReviewReceipt(input,{runId,result,now=new Date().toISOString()}) {
  const state=parseReviewState(input);
  if(!/^[0-9]{1,24}$/.test(String(runId)))
    throw new Error('Invalid radar run ID');
  const digest=receiptDigest(result);
  const previous=state.runs.find(r=>r.run_id===String(runId));
  if(previous){
    if(previous.digest!==digest)
      throw new Error('Conflicting radar review replay');
    return {state,added:0,already_committed:true};
  }
  if(!Number.isFinite(Date.parse(now)))throw new Error('Invalid review timestamp');
  const byId=new Map(state.observed.map(v=>[v.identity,v]));
  const roleKeys=new Set(state.observed.flatMap(v=>strongRoleKeys(v.official_url)));
  let added=0;
  for(const c of result.candidates){
    const url=canonicalUrl(c.official_url);
    if(!ID.test(c.observation_key)||url!==c.official_url||
       !strongRoleKeys(url).length||typeof c.title!=='string'||
       c.title.length===0||c.title.length>240)
      throw new Error('Invalid radar review candidate');
    const existing=byId.get(c.observation_key);
    if(existing){
      if(existing.official_url!==url)
        throw new Error('Conflicting radar identity in durable state');
      continue;
    }
    if(strongRoleKeys(url).some(k=>roleKeys.has(k)))continue;
    const item={identity:c.observation_key,official_url:url,
      title:c.title,first_seen_utc:now};
    byId.set(item.identity,item);
    for(const key of strongRoleKeys(url))roleKeys.add(key);
    added++;
  }
  if(byId.size>MAX_REVIEW_STATE_ITEMS||state.runs.length>=MAX_RUN_RECEIPTS)
    throw new Error('Radar review state capacity reached');
  const next={schema_version:1,
    observed:[...byId.values()].sort((a,b)=>a.identity.localeCompare(b.identity)),
    runs:[...state.runs,{run_id:String(runId),digest,completed_utc:now,
      count:result.candidates.length}]};
  parseReviewState(next);
  return {state:next,added,already_committed:false};
}
