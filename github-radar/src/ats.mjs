// Official ATS reads only. No D1, browser submission or provider mutation.
import {adapterUrl,isValidJob,normalizeJobs} from './logic.mjs';
const TIMEOUT_MS=10000;
const MAX_SOURCE_JOBS=160;
export async function publicJobs(source){
  const resp=await fetch(adapterUrl(source),{
    headers:{Accept:'application/json'},signal:AbortSignal.timeout(TIMEOUT_MS)
  });
  if(!resp.ok){
    const e=new Error('Official ATS HTTP '+resp.status);
    e.status=resp.status;
    throw e;
  }
  const declared=Number(resp.headers.get('content-length')||0);
  if(declared>2_000_000)throw new Error('Official ATS payload too large');
  const data=await resp.text();
  if(data.length>2_000_000)throw new Error('Official ATS payload too large');
  const jobs=normalizeJobs(source,JSON.parse(data));
  if(jobs.length>MAX_SOURCE_JOBS)throw new Error('Official ATS result exceeds bounded limit');
  if(!jobs.every(isValidJob))throw new Error('Official ATS response failed host/tenant validation');
  return jobs;
}
