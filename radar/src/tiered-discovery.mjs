// Optional manual fallback within the existing GitHub Radar, never a second scanner.
// Existing deploy manifest supplies the five vetted public API/RSS endpoints.
// Provider output is discovery evidence, NOT official vacancy verification.
const FEEDS=Object.freeze({
  'remotive':['remotive','discovery_api'],
  'jobicy-api':['jobicy','discovery_api'],
  'himalayas':['himalayas','discovery_api'],
  'we-work-remotely':['weworkremotely','job_board'],
  'remote-ok':['remoteok','job_board'],
  'remote-landers-api':['publicfeeds','discovery_api'],
  'remotejobs-org':['publicfeeds','discovery_api'],
  'arbeitnow-api':['publicfeeds','discovery_api']
});
const SAFE=/^[a-z0-9][a-z0-9_-]{1,79}$/;
export function selectTieredSources(specs){
  if(!Array.isArray(specs)||specs.length<1||specs.length>100)
    throw new Error('Invalid existing deploy source manifest');
  const selected=[],seen=new Set();
  for(const source of specs){
    if(!Object.hasOwn(FEEDS,source?.source_id))continue;
    const [adapter,type]=FEEDS[source.source_id];
    if(seen.has(source.source_id)||source.adapter!==adapter||source.source_type!==type||
       !SAFE.test(source.account||'')||!Number.isSafeInteger(source.max_jobs)||
       source.max_jobs<1||source.max_jobs>20000)
      throw new Error('Invalid public discovery source contract');
    const endpoint=source.endpoint;
    if(source.source_id==='remote-ok'&&endpoint!=='https://remoteok.com/api'||
       source.source_id==='we-work-remotely'&&
         endpoint!=='https://weworkremotely.com/categories/remote-programming-jobs.rss'||
       !['remote-ok','we-work-remotely'].includes(source.source_id)&&endpoint!==undefined)
      throw new Error('Invalid public discovery endpoint');
    seen.add(source.source_id);
    selected.push({source_id:source.source_id,source_type:type,account:source.account});
  }
  if(selected.length!==8)throw new Error('Missing approved public discovery adapters');
  return selected;
}
export function orderTieredSources(sources,meta,config){
  if(!(meta instanceof Map)||!(config instanceof Map)||sources.length>8)
    throw new Error('Invalid live discovery policy');
  const order=String(config.get('direct_discovery_order')||'').split(',').map(x=>x.trim());
  const high=String(config.get('high_source_order')||'').split(',').map(x=>x.trim());
  if(!order.includes('discovery_api')||!order.includes('job_board')||
     order.indexOf('discovery_api')>=order.indexOf('job_board'))
    throw new Error('Invalid live discovery policy');
  const enabled=[],skipped=[];
  for(const source of sources){
    const row=meta.get(source.source_id);
    if(!row||row.status!=='active'){
      skipped.push({source:source.source_id,reason:'inactive_or_unregistered'});
      continue;
    }
    if(!['discovery_api','job_board'].includes(row.type)||
       !['high','medium','low'].includes(row.priority))
      throw new Error('Invalid live discovery source class');
    enabled.push({...source,source_type:row.type,priority:row.priority});
  }
  const rank=x=>high.indexOf(x.source_id)>=0?high.indexOf(x.source_id):999;
  enabled.sort((a,b)=>order.indexOf(a.source_type)-order.indexOf(b.source_type)||
    (a.priority==='high'?0:a.priority==='medium'?1:2)-
    (b.priority==='high'?0:b.priority==='medium'?1:2)||
    rank(a)-rank(b)||a.source_id.localeCompare(b.source_id));
  return {enabled,skipped};
}
export async function collectTieredDiscovery({
  sources,skipped=[],maxCandidates,seenIds,seenRoles,register,fetchJobs,pollWithRetry,
  preliminaryInterest,preliminaryRemoteEvidence,preliminaryNetherlandsScope,
  matchRegister,strongRoleKeys,canonicalUrl,safeDiagnosticError,scanAll=false
}){
  const result={mode:'discovery_only',manual_official_verification_required:true,
    checked_sources:[],skipped_sources:[...skipped],not_polled_sources:[],
    counts:{observed:0,previously_seen:0,already_in_register:0,previously_applied:0,
      unrelated:0,remote_evidence_missing:0,geography_outside_nl:0,review_candidates:0},
    candidates:[],failures:[],eligible_not_queued:0};
  if(!Number.isSafeInteger(maxCandidates)||maxCandidates<0||maxCandidates>10)
    throw new Error('Invalid discovery review limit');
  for(const [i,source] of sources.entries()){
    if(!scanAll&&result.candidates.length>=maxCandidates){
      result.not_polled_sources=sources.slice(i).map(x=>x.source_id);
      break;
    }
    let jobs;
    try{
      jobs=await pollWithRetry(source,fetchJobs);
      if(!Array.isArray(jobs)||jobs.length>120)throw new Error('Unexpected public discovery payload');
      // Validate entire provider batch before using any lead from that source.
      for(const job of jobs){
        if(!job||job.source_id!==source.source_id||job.source_account!==source.account||
           !/^[a-f0-9]{24}$/.test(job.source_job_id||'')||
           job.identity!==source.source_id+':'+source.account+':'+job.source_job_id||
           typeof job.title!=='string'||!job.title.trim()||job.title.length>240||
           typeof job.url!=='string'||!canonicalUrl(job.url))
          throw new Error('Unexpected public discovery payload');
      }
    }catch(error){
      result.failures.push({source:source.source_id,reason:safeDiagnosticError(error)});
      continue;
    }
    result.checked_sources.push(source.source_id);
    result.counts.observed+=jobs.length;
    for(const job of jobs){
      const matched=matchRegister(job,register);
      const keys=strongRoleKeys(job.url);
      // Exact job-like links may use /remote-jobs/... rather than /jobs/...
      // This fallback is local-only: never persists as a verified role key.
      const clean=canonicalUrl(job.url);
      const segments=new URL(clean).pathname.split('/').filter(Boolean);
      if(segments.length>=2&&!['jobs','job','careers','career','search','apply',
        'positions','openings','remote-jobs'].includes(segments.at(-1).toLowerCase()))
        keys.push('discovery-url:'+clean);
      if(matched.applied)result.counts.previously_applied++;
      else if(matched.known)result.counts.already_in_register++;
      else if(seenIds.has(job.identity)||keys.some(k=>seenRoles.has(k)))
        result.counts.previously_seen++;
      else if(!preliminaryInterest(job))result.counts.unrelated++;
      else if(!preliminaryRemoteEvidence(job))result.counts.remote_evidence_missing++;
      else if(!preliminaryNetherlandsScope(job))result.counts.geography_outside_nl++;
      else {
        seenIds.add(job.identity);
        for(const key of keys)seenRoles.add(key);
        if(result.candidates.length>=maxCandidates){
          result.eligible_not_queued++;
          continue;
        }
        result.candidates.push({
          observation_key:job.identity,source_id:source.source_id,
          employer:String(job.employer||'').slice(0,160),title:job.title,
          discovery_url:canonicalUrl(job.url),source_url:String(job.source_url||'').slice(0,240),
          location:String(job.location||'').slice(0,160),remote_text:String(job.remote||'').slice(0,80),
          verification:'discovery_only; verify exact employer-owned ATS URL, authenticity, remote/NL, language and role fit before selection'
        });
      }
    }
  }
  result.counts.review_candidates=result.candidates.length;
  result.status=result.failures.length?'partial':'review_ready';
  result.stopped_when_manual_queue_full=result.not_polled_sources.length>0;
  return result;
}
