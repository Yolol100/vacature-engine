// Technical discovery only: authoritative policy and application status live in Vacature Register.
export const PILOT_SOURCES=Object.freeze([
  {source_id:'greenhouse',account:'automatticcareers',employer_source_id:'company-automattic',employer:'Automattic'},
  {source_id:'lever',account:'kinsta',employer_source_id:'company-kinsta',employer:'Kinsta'},
  {source_id:'ashby',account:'zapier',employer_source_id:'company-zapier',employer:'Zapier'}
]);
const TRACKING=new Set(['ref','source','campaign','gh_src','mc_cid','mc_eid','li_fat_id','referral']);
const APPLIED=new Set(['submitted','applied','screen','interview','assessment','final','offer','rejected','withdrawn','closed']);
const ALREADY_KNOWN=new Set(['seen','shown','submitted','applied','screen','interview','assessment','final','offer','rejected','withdrawn','closed','excluded_user_preference','excluded']);
// Only these two provider-confirmed employer-owned Greenhouse URL contracts.
const CUSTOM_GREENHOUSE=Object.freeze({
  'www.digitalocean.com':{tenant:'digitalocean98',path:'/careers/position/apply'},
  'pantheon.io':{tenant:'pantheon',path:'/about/careers/detail'}
});
function greenhouseCustomRole(url){
  const entry=CUSTOM_GREENHOUSE[url.hostname];
  if(!entry||url.protocol!=='https:'||url.username||url.password||url.port||
     (url.pathname.endsWith('/')?url.pathname.slice(0,-1):url.pathname)!==entry.path||
     url.searchParams.size!==1)return null;
  const ids=url.searchParams.getAll('gh_jid');
  if(ids.length!==1||!/^[1-9][0-9]{1,14}$/.test(ids[0]))return null;
  return {tenant:entry.tenant,id:ids[0]};
}
const INTEREST=/\b(wordpress|woocommerce|elementor|gutenberg|website|web[\s-]?(?:design(?:er|ing)?|develop(?:er|ment)?|engineer(?:ing)?|performance)|webdesign|webdevelopment|php[\s-]?(?:developer|engineer|programmer)|full[\s-]?stack|software[\s-]?(?:engineer|developer)|applied[\s-]?ai|product[\s-]?design(?:er|ing)?|design[\s-]?systems?|core[\s-]?web[\s-]?vitals?|ui[\s-]?design(?:er|ing)?|react|next\.js|front[\s-]?end|ui\/ux|ux\/ui|ux|accessibility|automation|automations|workflow|workflows|integrations?|n8n|zapier|make\.com|no[\s-]?code|cms|ai[\s-]?agent|technical[\s-]?seo)\b/i;

// A role previously parsed the same URL twice (canonicalize + inspect).
// Keep the exact canonicalization rules, using one validated URL instance.
function normalizedUrl(raw){
  if(typeof raw!=='string'||!raw.trim())return null;
  try{
    const url=new URL(raw.trim());
    if(url.protocol!=='https:'||url.username||url.password)return null;
    url.hash='';
    for(const key of [...url.searchParams.keys()]){
      if(key.toLowerCase().startsWith('utm_')||TRACKING.has(key.toLowerCase()))
        url.searchParams.delete(key);
    }
    url.pathname=url.pathname.replace(/\/+$/,'')||'/';
    url.hostname=url.hostname.toLowerCase();
    return url;
  }catch{return null;}
}
function canonicalString(url){return url.toString().replace(/\/$/,'');}
export function canonicalUrl(raw) {
  const url=normalizedUrl(raw);
  return url?canonicalString(url):'';
}
// Never treat a generic careers URL as a strong duplicate key.
// Provider-derived keys allow /apply variants and canonical ATS URL forms to match.
export function strongRoleKeys(raw) {
  const u=normalizedUrl(raw);
  if(!u)return [];
  const url=canonicalString(u),host=u.hostname.toLowerCase(),segments=u.pathname.split('/').filter(Boolean);
  const keys=new Set();
  let ats='';
  if((host==='jobs.lever.co'||host==='jobs.eu.lever.co')&&segments.length>=2)
    ats='ats:lever:'+segments[0].toLowerCase()+':'+segments[1].toLowerCase();
  else if(host==='jobs.ashbyhq.com'&&segments.length>=2)
    ats='ats:ashby:'+segments[0].toLowerCase()+':'+segments[1].toLowerCase();
  else if((host==='boards.greenhouse.io'||host==='job-boards.greenhouse.io')&&segments.length>=2){
    const id=segments[1]==='jobs'?segments[2]:segments[1];
    if(id)ats='ats:greenhouse:'+segments[0].toLowerCase()+':'+id.toLowerCase();
  }
  else if(host==='apply.workable.com'&&segments.length===3&&segments[1]==='j')
    ats='ats:workable:'+segments[0].toLowerCase()+':'+segments[2].toLowerCase();
  else if(host.endsWith('.jobs.personio.com')&&segments.length===2&&segments[0]==='job'){
    const tenant=host.slice(0,-'.jobs.personio.com'.length);
    if(tenant&&!tenant.includes('.'))
      ats='ats:personio:'+tenant+':'+segments[1].toLowerCase();
  }
  const custom=greenhouseCustomRole(u);
  if(custom)ats='ats:greenhouse:'+custom.tenant+':'+custom.id;
  if(ats){keys.add(ats);keys.add('url:'+url);return [...keys];}
  if(segments.length<2)return [];
  const path=u.pathname.toLowerCase();
  const hasRolePath=/(?:^|\/)(?:job|jobs|o|opening|openings|position|positions|vacature|vacatures|careers|career|apply)\//.test(path);
  const last=segments.at(-1).toLowerCase();
  if(!hasRolePath||['jobs','careers','career','positions','vacatures','apply','search','openings'].includes(last))return [];
  keys.add('url:'+url);
  return [...keys];
}
function addKeys(set,raw){for(const key of strongRoleKeys(raw))set.add(key);}
export function activeSourcePairs(rows,sources){
  // Source registry can contain hundreds of rows; build the map once per poll.
  const states=new Map();
  for(let i=1;i<rows.length;i++){
    const row=rows[i];
    if(row?.[0])states.set(row[0],row[12]);
  }
  return sources.filter(source=>
    states.get(source.source_id)==='active'&&states.get(source.employer_source_id)==='active');
}
export function sourceActive(rows,source){
  return activeSourcePairs(rows,[source]).length===1;
}
export function preliminaryInterest(job){
  // Hybrid/onsite jobs cannot pass the live fully-remote gate.
  // Missing evidence remains unknown until verified by vacature-search.
  if(/^(?:hybrid|on[-_ ]?site|in[-_ ]?office|office)$/i.test(String(job.remote||'').trim()))
    return false;
  return INTEREST.test([job.title,job.remote,job.location].join(' '));
}
// Candidate-queue relevance is only a first-pass user-family check. Full fit,
// language, official publication and NL remote policy require specialist review.
const TARGET_ROLE_TITLE=/\b(?:wordpress|woocommerce|elementor|gutenberg|acf|wp[- ]?cli|wp\s+engine|wpengine|yoast|n8n|make\.com|zapier|automation|automations|workflow|workflows|ai[- ]?(?:agents?|integrations?)|api[- ]?integrations?|systems?[- ]?integrations?)\b/i;
export function targetFamilyInterest(job){
  return TARGET_ROLE_TITLE.test(String(job?.title||''))&&preliminaryInterest(job);
}
export function normalizeJobs(source,payload){
  const jobs=Array.isArray(payload)?payload:payload?.jobs;
  if(!Array.isArray(jobs))throw new Error('Unexpected public jobs payload');
  return jobs.filter(job=>!(source.source_id==='ashby'&&job.isListed===false)).map(job=>{
    const sourceUrl=source.source_id==='lever'?job.hostedUrl:source.source_id==='ashby'?job.jobUrl:job.absolute_url;
    const url=canonicalUrl(sourceUrl||'');
    const id=String(job.id??(source.source_id==='ashby'?url:'')).trim();
    const title=String(source.source_id==='lever'?job.text??'':job.title??'').trim();
    const location=String(source.source_id==='lever'?job.categories?.location??'':typeof job.location==='string'?job.location:job.location?.name??'').trim();
    const remote=String(job.workplaceType??(job.isRemote===true?'remote':'')).trim();
    // Only an explicit publication timestamp from the official ATS counts.
    // Lever createdAt / Greenhouse updated_at are not publication evidence.
    const officialPublished=source.source_id==='ashby'?job.publishedAt:
      source.source_id==='greenhouse'?job.first_published:null;
    const parsedPublished=typeof officialPublished==='string'&&
      /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(officialPublished)?
      Date.parse(officialPublished):NaN;
    const confirmedPublished=Number.isFinite(parsedPublished)?
      new Date(parsedPublished).toISOString():'';
    return {
      identity:source.source_id+':'+source.account+':'+id,source_id:source.source_id,source_account:source.account,source_job_id:id,
      employer:source.employer,title,url,source_url:url,location,remote,language:'',
      // First-seen is NEVER employer publication evidence.
      confirmed_published_at:confirmedPublished
    };
  }).filter(job=>job.source_job_id&&job.title&&job.url);
}
export function buildRegisterIndex(vacatures,applications,events){
  const known=new Set(),applied=new Set(),vacancyById=new Map(),submittedIds=new Set();
  for(const row of vacatures.slice(1)){
    const id=String(row[0]||'');
    if(!id||/^(?:test:|history:)/i.test(id))continue;
    vacancyById.set(id,row);
    if(ALREADY_KNOWN.has(String(row[1]||'').toLowerCase())){
      addKeys(known,row[6]);addKeys(known,row[7]);
    }
    if(APPLIED.has(String(row[1]||'').toLowerCase())&&['submitted','applied'].includes(String(row[1]||'').toLowerCase()))submittedIds.add(id);
  }
  for(const row of events.slice(1)){
    const id=String(row[1]||'');
    if(!id||/^(?:test:|history:)/i.test(id))continue;
    if(String(row[3]||'').toLowerCase()==='submitted'||String(row[5]||'').toLowerCase()==='submitted')submittedIds.add(id);
  }
  const applicationRows=[];
  for(const row of applications.slice(1)){
    const id=String(row[0]||'');
    if(!id){
      // A submitted application may have no vacancy ID yet, but its
      // canonical role URL is still strong evidence against resurfacing it.
      if(APPLIED.has(String(row[2]||'').toLowerCase()))
        addKeys(applied,row[4]);
      continue;
    }
    if(/^(?:test:|history:)/i.test(id))continue;
    applicationRows.push(row);
    if(APPLIED.has(String(row[2]||'').toLowerCase()))submittedIds.add(id);
  }
  for(const id of submittedIds){
    const vacancy=vacancyById.get(id);
    if(vacancy){addKeys(applied,vacancy[6]);addKeys(applied,vacancy[7]);}
  }
  for(const row of applicationRows){
    if(!submittedIds.has(String(row[0]||'')))continue;
    addKeys(applied,row[4]);
  }
  for(const key of applied)known.add(key);
  return {known,applied};
}
export function matchRegister(job,index){
  const keys=new Set(strongRoleKeys(job.url));
  // ATS normalization already assigns source_url=url; avoid duplicate parsing.
  if(job.source_url!==job.url)for(const key of strongRoleKeys(job.source_url))keys.add(key);
  if(job.source_id&&job.source_job_id){
    keys.add('ats:'+job.source_id+':'+String(job.identity||'').split(':').slice(1,-1).join(':').toLowerCase()+':'+String(job.source_job_id).toLowerCase());
  }
  return {applied:[...keys].some(k=>index.applied.has(k)),known:[...keys].some(k=>index.known.has(k))};
}
export function toRadarRow(job,now,runId){
  return [job.identity,job.source_id,job.source_job_id,job.employer,job.title,job.url,job.source_url,
    job.remote,job.location,job.language,job.confirmed_published_at,now,now,
    'onbekend','ontdekt','onbekend','niet_beoordeeld','officiele_verificatie_nodig',
    'Technische ontdekking; publicatiedatum onbekend; nog geen bewezen vacaturematch.','',runId];
}
export function adapterUrl(source){
  if(source.source_id==='greenhouse')return 'https://boards-api.greenhouse.io/v1/boards/'+encodeURIComponent(source.account)+'/jobs';
  if(source.source_id==='lever')return 'https://api.lever.co/v0/postings/'+encodeURIComponent(source.account)+'?mode=json';
  if(source.source_id==='ashby')return 'https://api.ashbyhq.com/posting-api/job-board/'+encodeURIComponent(source.account);
  throw new Error('Unsupported adapter');
}
export function isValidJob(job){
  if(!job.identity||!job.url||!job.title||!job.source_job_id)return false;
  const url=new URL(job.url);
  const host=url.hostname, parts=url.pathname.split('/').filter(Boolean);
  const expectedTenant=String(job.source_account||'').toLowerCase();
  if(!expectedTenant)return false;
  // Greenhouse may return an official employer URL with a gh_jid post ID.
  // Only the two exact employer/tenant/path contracts above are trusted.
  if(job.source_id==='greenhouse'){
    const custom=greenhouseCustomRole(url);
    if(custom)return custom.tenant===expectedTenant&&
      custom.id===String(job.source_job_id);
  }
  if(job.source_id==='personio')return host===expectedTenant+'.jobs.personio.com'&&
    parts.length===2&&parts[0]==='job'&&
    parts[1].toLowerCase()===String(job.source_job_id).toLowerCase();
  if(parts[0]?.toLowerCase()!==expectedTenant)return false;
  if(job.source_id==='workable')return host==='apply.workable.com'&&
    parts.length===3&&parts[1]==='j'&&
    parts[2].toLowerCase()===String(job.source_job_id).toLowerCase();
  if(job.source_id==='greenhouse')return (host==='boards.greenhouse.io'||host==='job-boards.greenhouse.io')&&
    parts[1]==='jobs'&&parts.length>=3&&
    parts[2].toLowerCase()===String(job.source_job_id).toLowerCase();
  if(job.source_id==='lever')return (host==='jobs.lever.co'||host==='jobs.eu.lever.co')&&
    parts.length>=2&&parts[1].toLowerCase()===String(job.source_job_id).toLowerCase();
  if(job.source_id==='ashby')return host==='jobs.ashbyhq.com'&&parts.length>=2;
  return false;
}
export function chooseSource(sources,minuteIndex){return sources.length?sources[((minuteIndex%sources.length)+sources.length)%sources.length]:null;}
export function cooldownMinutes(failures,httpStatus,retryAfterSeconds){
  const baseline=httpStatus===429?15:Math.min(60,3*2**Math.min(6,Math.max(0,failures-1)));
  const hinted=Number.isFinite(retryAfterSeconds)?Math.ceil(Math.max(0,retryAfterSeconds)/60):0;
  return Math.min(525600,Math.max(baseline,hinted));
}
export function runStatsRow(runId,start,end,m){
  return [runId,start,end,m.sources,m.observations,m.delivered,m.known,m.applied,m.skipped,m.errors.length,m.errors.length?'partial':m.sources===0?'cooldown':'ok',m.errors.join('; ').slice(0,500)];
}
