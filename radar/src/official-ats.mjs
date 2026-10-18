// Read-only official ATS reader.
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {adapterUrl,isValidJob,normalizeJobs} from './logic.mjs';
function bridgeError(error,kind){
  const stderr=String(error?.stderr||'');
  const status=/public_ats_http_([45][0-9][0-9])/.exec(stderr)?.[1];
  const fetch=/public_ats_fetch_(timeout_or_network|malformed_result|response_too_large|rate_limited|upstream_transient|blocked_or_auth_required|other_technical_failure|http_error)/.exec(stderr)?.[1];
  const reason=status?'Public API HTTP '+status:
    fetch?'Public API fetch '+fetch:
    stderr.includes('public_ats_contract_error')?'Public API contract mismatch':
    stderr.includes('public_ats_internal_error')?'Public API adapter internal failure':
    kind==='ats'?'Public ATS adapter failed':'Public discovery adapter failed';
  const safe=new Error(reason);
  if(status)safe.status=Number(status);
  return safe;
}
const MAX_SOURCE_JOBS=160;
const TIMEOUT_MS=10000;
async function publicJobs(source,limits={}){
  // Conservative defaults; manual reviews may request a larger bounded feed.
  const maxJobs=limits.maxJobs??MAX_SOURCE_JOBS;
  const maxBytes=limits.maxBytes??2_000_000;
  if(!Number.isSafeInteger(maxJobs)||maxJobs<1||maxJobs>1000||
     !Number.isSafeInteger(maxBytes)||maxBytes<1||maxBytes>6_000_000)
    throw new Error('Invalid bounded ATS limits');
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
  if(declared>maxBytes)throw new Error('Source payload too large');
  const body=await resp.text();
  if(body.length>maxBytes)throw new Error('Source payload too large');
  const items=normalizeJobs(source,JSON.parse(body));
  if(items.length>maxJobs)throw new Error('Source exceeds safe job limit');
  const valid=items.filter(isValidJob);
  if(valid.length!==items.length)throw new Error('Unexpected ATS job host: source contract changed');
  return valid;
}
export {publicJobs};

// Read-only Node bridge for Personio/Workable via existing ingestion adapters.
const execFileAsync=promisify(execFile);
export async function actionsPublicJobs(source,limits={maxJobs:1000,maxBytes:6_000_000}) {
  if(!['personio','workable'].includes(source.source_id))
    return publicJobs(source,limits);
  if(!Number.isSafeInteger(limits.maxJobs)||limits.maxJobs<1||limits.maxJobs>1000)
    throw new Error('Invalid bounded ATS limits');
  let stdout;
  try{
    ({stdout}=await execFileAsync('python3',[
      '-m','vacature_ingestion.actions_readonly_bridge',
      source.source_id,source.account,source.employer
    ],{
      // Never forward the service-account secret to a public ATS child process.
      env:{PATH:process.env.PATH,PYTHONPATH:'ingestion/src',PYTHONIOENCODING:'utf-8'},
      timeout:20_000,maxBuffer:6_000_000
    }));
  }catch(error){
    throw bridgeError(error,'ats');
  }
  let data;
  try{data=JSON.parse(stdout);}catch{throw new Error('Unexpected public ATS payload');}
  if(!Array.isArray(data?.jobs)||data.jobs.length>limits.maxJobs)
    throw new Error('Unexpected public ATS payload');
  return data.jobs;
}

// This path has no credentials and cannot write state; provider data stays unverified.
// Each read is a bounded child process reusing the five pre-existing Python adapters.
export async function actionsPublicDiscoveryJobs(source) {
  if(!['remotive','jobicy-api','himalayas','we-work-remotely','remote-ok',
      'remote-landers-api','remotejobs-org','arbeitnow-api'].includes(source?.source_id))
    throw new Error('Unsupported public discovery source');
  let stdout;
  try {
    ({stdout}=await execFileAsync('python3',[
      '-m','vacature_ingestion.actions_readonly_bridge','--discovery',source.source_id
    ],{
      env:{PATH:process.env.PATH,PYTHONPATH:'ingestion/src',PYTHONIOENCODING:'utf-8'},
      timeout:30000,maxBuffer:2_000_000
    }));
  }catch(error){
    throw bridgeError(error,'discovery');
  }
  let parsed;
  try{parsed=JSON.parse(stdout);}catch{throw new Error('Unexpected public discovery payload');}
  if(!Array.isArray(parsed?.jobs)||parsed.jobs.length>120)
    throw new Error('Unexpected public discovery payload');
  return parsed.jobs;
}
