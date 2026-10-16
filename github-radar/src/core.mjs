import {
  PILOT_SOURCES,activeSourcePairs,buildRegisterIndex,matchRegister,
  preliminaryInterest,strongRoleKeys,canonicalUrl
} from './logic.mjs';

export const STATE_HEADER=Object.freeze([
  'identity','source_instance','official_url','status','first_seen_at'
]);
export const RADAR_RANGES=Object.freeze([
  "'Nieuwe vacatures'!A1:A","'Nieuwe vacatures'!F1:F"
]);
function insist(value,message){if(!value)throw new Error(message);}
export function assessRadar({register,radarValues,stateRows,sourceJobs,generatedAt}){
  insist(Array.isArray(register)&&register.length===4,'Incomplete register');
  const [sources,vacancies,applications,events]=register;
  insist(sources?.[0]?.[0]==='source_id'&&sources[0][12]==='status',
    'Source register header mismatch');
  insist(vacancies?.[0]?.[0]==='vacancy_id','Vacatures header mismatch');
  insist(applications?.[0]?.[0]==='vacancy_id','Applications header mismatch');
  insist(events?.[0]?.[0]==='event_id','ApplicationEvents header mismatch');
  insist(Array.isArray(radarValues)&&radarValues.length===2&&
    radarValues[0]?.[0]?.[0]==='observation_key'&&
    radarValues[1]?.[0]?.[0]==='officiele_url',
    'Radar output header mismatch');
  insist(Array.isArray(stateRows)&&STATE_HEADER.every((h,i)=>stateRows[0]?.[i]===h),
    'Radar State header mismatch (migrate before scanning)');
  const previous=new Set(),previousUrls=new Set(),sourcesInState=new Set();
  for(const row of stateRows.slice(1)){
    const id=String(row?.[0]||''),url=canonicalUrl(row?.[2]||'');
    insist(id&&url&&['baseline','reviewed','excluded','delivered'].includes(row?.[3]),
      'Radar State contains malformed identity, URL or status');
    insist(!previous.has(id),'Radar State has duplicate identities');
    previous.add(id);
    sourcesInState.add(String(row[1]||''));
    for(const key of strongRoleKeys(url))previousUrls.add(key);
  }
  // Migrated 26-row baseline is the sole trusted bootstrapping evidence.
  // New sources must not be automatically treated as new without a baseline.
  for(const source of PILOT_SOURCES){
    insist(sourcesInState.has(source.source_id+':'+source.account),
      'Missing migrated baseline for '+source.source_id+':'+source.account);
  }
  const active=activeSourcePairs(sources,PILOT_SOURCES);
  insist(active.length>0,'No active registered ATS and employer pair');
  const outputKeys=new Set(radarValues[0].slice(1).map(r=>r?.[0]).filter(Boolean));
  const outputUrls=new Set();
  for(const row of radarValues[1].slice(1))
    for(const key of strongRoleKeys(row?.[0]))outputUrls.add(key);
  const reg=buildRegisterIndex(vacancies,applications,events);
  insist(Array.isArray(sourceJobs)&&sourceJobs.length===active.length,
    'Missing active source ATS result');
  const activeIds=new Set(active.map(x=>x.source_id+':'+x.account));
  const candidates=[],seen=new Set(),metrics={
    sources:active.length,official_jobs:0,baseline:0,already_known:0,
    previously_applied:0,not_targeted:0,requires_manual_review:0
  };
  for(const response of sourceJobs){
    const instance=response?.instance;
    insist(activeIds.has(instance)&&!seen.has('source:'+instance),
      'Unexpected, inactive or duplicate ATS source response');
    seen.add('source:'+instance);
    insist(Array.isArray(response.jobs)&&response.jobs.length<=160,
      'Missing or over-limit ATS data');
    for(const job of response.jobs){
      insist(job.identity&&job.url&&job.title&&job.source_id&&job.source_job_id,
        'Invalid official ATS job');
      metrics.official_jobs++;
      const identity=job.identity,keys=strongRoleKeys(job.url);
      insist(keys.length>0,'Official ATS identity lacks strong role URL');
      if(previous.has(identity)||keys.some(k=>previousUrls.has(k))){
        metrics.baseline++;continue;
      }
      const m=matchRegister(job,reg);
      if(m.applied){metrics.previously_applied++;continue;}
      if(m.known||outputKeys.has(identity)||keys.some(k=>outputUrls.has(k))){
        metrics.already_known++;continue;
      }
      if(seen.has('job:'+identity)||keys.some(k=>seen.has('key:'+k))){
        metrics.already_known++;continue;
      }
      seen.add('job:'+identity);
      for(const k of keys)seen.add('key:'+k);
      if(!preliminaryInterest(job)){metrics.not_targeted++;continue;}
      // Do not assert a final match, Netherlands, remote, language or publication
      // date: these fields need human and live authoritative verification.
      candidates.push({
        identity,title:job.title,employer:job.employer,official_url:job.url,
        source:instance,location:job.location||'',workplace:job.remote||'',
        manual_review_required:true,authenticity:'official_ats',
        fit:'unverified',publication_date:'unverified',
        application_action:'none'
      });
    }
  }
  insist(seen.size>=active.length,'No source responses handled');
  metrics.requires_manual_review=candidates.length;
  return {schema_version:1,mode:'review_only',generated_at:generatedAt,
    source_of_truth:'Vacature Register (Google Sheets)',
    baseline_state:'Radar State (Google Sheets)',metrics,candidates,
    writes_to_business_sheets:0,application_submissions:0};
}
