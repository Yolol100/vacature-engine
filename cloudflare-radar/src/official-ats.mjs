// Shared official ATS reader and exact D1 identity lookup.
import {adapterUrl,isValidJob,normalizeJobs} from './logic.mjs';
const MAX_SOURCE_JOBS=160;
const TIMEOUT_MS=10000;
function params(n){return Array.from({length:n},()=>'?').join(',');}
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
export {publicJobs,existingKeys,params};
