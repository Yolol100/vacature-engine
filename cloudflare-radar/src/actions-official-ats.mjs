// Actions-only bridge. The Cloudflare Worker continues using its existing
// three JavaScript adapters; Personio/Workable reuse the ingestion adapters.
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {publicJobs} from './official-ats.mjs';

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
    const status=/public_ats_http_([45][0-9][0-9])/.exec(String(error?.stderr||''))?.[1];
    const safe=new Error(status?'Public API HTTP '+status:'Public ATS adapter failed');
    if(status)safe.status=Number(status);
    throw safe;
  }
  let data;
  try{data=JSON.parse(stdout);}catch{throw new Error('Unexpected public ATS payload');}
  if(!Array.isArray(data?.jobs)||data.jobs.length>limits.maxJobs)
    throw new Error('Unexpected public ATS payload');
  return data.jobs;
}
