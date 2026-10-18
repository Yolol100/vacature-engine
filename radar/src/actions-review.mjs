// Node.js review-only successor to the Cloudflare poll. NO external writes.
import {PILOT_SOURCES,buildRegisterIndex,matchRegister,preliminaryInterest,targetFamilyInterest,strongRoleKeys,canonicalUrl,isValidJob} from './logic.mjs';
import {safeDiagnosticError} from './health.mjs';
import {parseReviewState} from './review-state.mjs';
import {orderTieredSources,collectTieredDiscovery} from './tiered-discovery.mjs';
export const MAX_REVIEW=10;


export function preliminaryRemoteEvidence(job){
  const text=[job?.location||'',job?.remote||''].join(' ').toLowerCase();
  // Workplace policy beats a loose "remote" mention; still only triage.
  if(/\b(?:hybrid|on[- ]?site|in[- ]?office|office[- ]?based)\b/.test(text))
    return false;
  return /\b(?:remote|work(?:ing)? from home|home[- ]?based|telecommut(?:e|ing)|anywhere|worldwide|distributed)\b/.test(text);
}

// Provider locations can use any ISO country, including NL and EN names.
// A one-country remote restriction is NOT proof of Netherlands eligibility.
const GEO_COUNTRY_NAMES=(()=>{
  const names=new Set();
  const normalize=x=>String(x).normalize('NFKD').replace(/\p{M}/gu,'')
    .toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  for(const locale of ['en','nl']){
    const display=new Intl.DisplayNames([locale],{type:'region'});
    for(let a=65;a<=90;a++)for(let b=65;b<=90;b++){
      const code=String.fromCharCode(a,b);
      if(['EU','UN','EZ','QO'].includes(code))continue;
      const label=display.of(code);
      if(label!==code&&label.length>=4)names.add(normalize(label));
    }
  }
  return [...names].filter(Boolean);
})();
function containsCountryOnly(place){
  const words=' '+place.normalize('NFKD').replace(/\p{M}/gu,'')
    .replace(/[^a-z0-9]+/g,' ').trim()+' ';
  return GEO_COUNTRY_NAMES.some(name=>words.includes(' '+name+' '));
}

// Conservative *triage only*. A foreign-country-only ATS location must not
// consume the ten-slot manual queue for a Netherlands-based applicant.
// Unknown / broad "Remote" is still UNVERIFIED, never an NL eligibility claim.
export function preliminaryNetherlandsScope(job){
  const place=String(job?.location||'').toLowerCase().replace(/[–—]/g,'-').trim();
  if(!place)return true;
  // An explicit employer exclusion outranks broad "global"/"Europe" wording.
  if(/\b(?:except|excluding|not in|outside|not available in)\s+(?:the\s+)?(?:netherlands|nederland)\b/.test(place))
    return false;
  if(/\b(?:netherlands|nederland|holland|amsterdam|rotterdam|utrecht|eindhoven|nl)\b/.test(place))
    return true;
  if(/\b(?:worldwide|anywhere|global(?:ly)?|europe|european union|europese unie|emea|eea)\b/.test(place))
    return true;
  // Verified live negative cases + other unambiguous single-country locations.
  // Lack of a match only means "unknown, requires specialist review".
  const abroad=/\b(?:costa rica|united kingdom|england|scotland|wales|uk|united states|usa|us|canada|india|bengaluru|bangalore|hyderabad|israel|australia|new zealand|singapore|philippines|south africa|brazil|mexico|argentina|colombia|japan|south korea|uae|united arab emirates|seattle|boston|san francisco|austin|denver|new york|nyc|toronto|vancouver|montreal|london|berlin|sofia|bulgaria|germany|france|spain|poland|romania|portugal|austria|italy|sweden|switzerland|belgium|ireland)\b/;
  return !abroad.test(place)&&
    !/\b(?:americas|latam|latin america|latin american|apac|asia pacific|north america|northern america|north american|middle east)\b/.test(place)&&
    !containsCountryOnly(place);
}
// Read the existing ingestion radar manifest instead of hardcoding a second
// production source list. Only adapters already shared with the Cloudflare
// reader are selected; unsupported adapters remain explicitly out of scope.
const ACTIONS_ADAPTERS=new Set(['greenhouse','lever','ashby','personio','workable']);
const SOURCE_TOKEN=/^[a-z0-9][a-z0-9_-]{1,79}$/;
export function selectSupportedSources(specs){
  if(!Array.isArray(specs)||specs.length===0||specs.length>100)
    throw new Error('Invalid radar source manifest');
  const sources=[],unsupported=[],unverified=[],seen=new Set();
  for(const spec of specs){
    if(!spec||typeof spec!=='object'||Array.isArray(spec)||
       typeof spec.source_id!=='string'||typeof spec.adapter!=='string')
      throw new Error('Invalid radar source specification');
    if(!ACTIONS_ADAPTERS.has(spec.adapter)){
      unsupported.push(spec.source_id);
      continue;
    }
    const owner=spec.options?.registry_source_id;
    if(spec.source_type!=='ats'||spec.source_id!==spec.adapter||
       !SOURCE_TOKEN.test(spec.account||'')||!SOURCE_TOKEN.test(owner||'')||
       typeof spec.employer!=='string'||!spec.employer.trim()||
       spec.employer.length>120)
      throw new Error('Invalid supported radar source specification');
    const key=spec.source_id+':'+spec.account.toLowerCase();
    if(seen.has(key))throw new Error('Duplicate radar source specification');
    seen.add(key);
    const contract=spec.options?.actions_review_host_contract;
    if(contract==='unverified'){
      // Provider returns URLs outside the strict official ATS tenant contract.
      // Do not weaken canonical URL verification to force this source through.
      unverified.push(key);
      continue;
    }
    if(contract!==undefined&&contract!=='verified')
      throw new Error('Invalid radar source host contract');
    sources.push({source_id:spec.source_id,account:spec.account,
      employer_source_id:owner,employer:spec.employer});
  }
  if(!sources.length||sources.length>30)
    throw new Error('No bounded supported radar sources');
  return {sources,unsupported,unverified};
}
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
export async function reviewOnce({env,accessToken,readRanges,publicJobs,maxCandidates=5,priorState,
  sources=PILOT_SOURCES,unsupportedSources=[],unverifiedSources=[],
  tieredSources=[],publicDiscoveryJobs=null,scanAllDiscovery=false}) {
  const reviewHistory=parseReviewState(priorState);
  if(!Array.isArray(sources)||sources.length===0||sources.length>30||
     !Array.isArray(unsupportedSources)||unsupportedSources.length>100||
     !Array.isArray(unverifiedSources)||unverifiedSources.length>100)
    throw new Error('Invalid bounded radar source scope');
  if(!Array.isArray(tieredSources)||tieredSources.length>8||
     (tieredSources.length>0&&typeof publicDiscoveryJobs!=='function'))
    throw new Error('Invalid bounded discovery scope');
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
        Number(/^Sheets read HTTP ([45][0-9][0-9])$/.exec(String(err?.message||''))?.[1]);
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
  const enabled=sources.filter(x=>active.get(x.source_id)==='active'&&
    active.get(x.employer_source_id)==='active');
  if(enabled.length===0)throw new Error('No active registered source pair');
  const register=buildRegisterIndex(vacancyRows,applicationRows,eventRows);
  // Only expanded manual reviews read the extra live source type/priority data.
  // The existing ATS-only/checkpoint paths use precisely the prior read contract.
  let enabledDiscovery=[],skippedDiscovery=[];
  const sourceMeta=new Map();
  if(tieredSources.length){
    const extra=await readRanges(env.VACATURE_REGISTER_ID,
      ["'Bronnen'!C1:C","'Bronnen'!E1:E"],token);
    if(!Array.isArray(extra)||extra.length!==2||
       extra[0]?.[0]?.[0]!=='source_type'||extra[1]?.[0]?.[0]!=='priority')
      throw new Error('Radar discovery source metadata unavailable');
    const meta=new Map();
    for(let i=1;i<sourceRows.length;i++){
      const id=String(sourceRows[i]?.[0]||'');
      if(!id)continue;
      meta.set(id,{type:extra[0][i]?.[0],priority:extra[1][i]?.[0],
        status:sourceRows[i][12]});
    }
    for(const [key,value] of meta)sourceMeta.set(key,value);
    const ordered=orderTieredSources(tieredSources,meta,config);
    enabledDiscovery=ordered.enabled;
    skippedDiscovery=ordered.skipped;
  }
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
    unrelated:0,remote_evidence_missing:0,geography_outside_nl:0,review_candidates:0};
  for(const source of enabled) {
    let jobs;
    try {
      jobs=await pollWithRetry(source,publicJobs);
      if(!Array.isArray(jobs)||jobs.length>1000)throw new Error('Unexpected public jobs payload');
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
      else if(!preliminaryInterest(job)||
        (env.RADAR_RUN_MODE==='quarter_hour_readonly'&&!targetFamilyInterest(job)))counts.unrelated++;
      else if(!preliminaryRemoteEvidence(job))counts.remote_evidence_missing++;
      else if(!preliminaryNetherlandsScope(job))counts.geography_outside_nl++;
      else {
        for(const k of roleKeys)seenRoles.add(k);
        seenIds.add(job.identity);
        if(candidates.length<maxCandidates)candidates.push({
          observation_key:job.identity,source_id:job.source_id,
          source_account:job.source_account,source_job_id:job.source_job_id,
          employer:source.employer,
          title:String(job.title).slice(0,240),official_url:job.url,
          location:String(job.location||'').slice(0,160),remote_text:String(job.remote||'').slice(0,160),
          confirmed_published_at:String(job.confirmed_published_at||'').slice(0,45),
          verification:'official_ats_observed; manual authenticity, remote/NL eligibility and fit review required'
        });
      }
    }
  }
  counts.review_candidates=candidates.length;
  // Phase 2/3 is strictly discovery-only. Unverified board results never enter
  // the official ATS queue or persistent checkpoint/receipt state.
  const discovery=tieredSources.length?await collectTieredDiscovery({
    sources:enabledDiscovery,skipped:skippedDiscovery,
    maxCandidates:scanAllDiscovery?maxCandidates:Math.max(0,maxCandidates-candidates.length),
    seenIds,seenRoles,register,fetchJobs:publicDiscoveryJobs,pollWithRetry,
    preliminaryInterest,preliminaryRemoteEvidence,preliminaryNetherlandsScope,
    matchRegister,strongRoleKeys,canonicalUrl,safeDiagnosticError,
    scanAll:scanAllDiscovery
  }):null;
  const result={schema_version:1,status:failures.length||discovery?.failures.length?
      'partial':'review_ready',
    mode:'read_only',manual_review_required:true,register_authoritative:true,
    baseline_records_read:baseline.ids.size,
    durable_review_observations:reviewHistory.observed.length,
    google_sheet_rows_written:0,application_submissions:0,
    active_sources:enabled.length,configured_sources:sources.length,
    unsupported_source_adapters:unsupportedSources.length,
    unverified_source_contracts:unverifiedSources.length,
    counts,candidates,failures};
  if(discovery){
    // High-priority web-only sources are explicit human handoff hints, NOT
    // automatically polled feeds. No invented API/ATS integrations.
    const automated=new Set([...sources.map(x=>x.source_id),
      ...tieredSources.map(x=>x.source_id)]);
    discovery.manual_fallback_sources=String(config.get('high_source_order')||'')
      .split(',').map(x=>x.trim()).filter(id=>id&&active.get(id)==='active'&&
        !automated.has(id)).slice(0,10);
    if(scanAllDiscovery){
      const activeTypes={},unautomatedTypes={};
      let registeredActive=0,automatedActive=0;
      const mapped=new Set([...sources.map(x=>x.employer_source_id),
        ...sources.map(x=>x.source_id),...tieredSources.map(x=>x.source_id)]);
      for(const [id,meta] of sourceMeta){
        if(meta.status!=='active')continue;
        registeredActive++;
        const type=String(meta.type||'unknown');
        activeTypes[type]=(activeTypes[type]||0)+1;
        if(mapped.has(id))automatedActive++;
        else unautomatedTypes[type]=(unautomatedTypes[type]||0)+1;
      }
      discovery.registry_coverage={
        active_registered:registeredActive,
        automated_identifiers:automatedActive,
        manual_or_other_identifiers:registeredActive-automatedActive,
        registered_types:activeTypes,
        manual_or_other_types:unautomatedTypes,
        complete_automatic_coverage:false
      };
    }
    result.discovery=discovery;
  }
  return result;
}
