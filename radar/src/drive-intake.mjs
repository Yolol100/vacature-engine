// Append-only, strictly bounded intake into the existing private Radar Google Sheet.
// Employer/ATS observations are never application approvals or verified matches.
// The Vacature Register remains authoritative for applications and candidate evidence.
import {readFileSync} from 'node:fs';
import {createHash,sign} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {buildRegisterIndex,matchRegister,isValidJob,strongRoleKeys} from './logic.mjs';

export const INTAKE_HEADERS=[
  'observation_key','source_id','source_job_id','werkgever','functietitel',
  'officiele_url','bron_url','remote_tekst','locatie','taal',
  'publicatie_bevestigd_utc','eerste_detectie_utc','laatste_detectie_utc',
  'sollicitatiehistorie','verificatie_status','nl_uitvoerbaar',
  'match_status','actie','opmerkingen','content_hash','run_id'
];
const RESULT_SHEET_ID='1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ';
const REGISTER_ID='1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0';
const MAX_AGE_MS=7*86400*1000;
const MAX_CANDIDATES=10;
const SCOPE='https://www.googleapis.com/auth/spreadsheets';
const API='https://sheets.googleapis.com/v4/spreadsheets/';
const TITLE_FAMILY=/\b(?:wordpress|woo(?:\s|-)commerce|elementor|gutenberg|acf|workflow automation|automated workflows?|business automation|process automation|ai automation|automation specialist|automation engineer|n8n|make\.com|zapier)\b/i;
const MAX_BYTES=2_000_000;

function utcDate(value){
  if(typeof value!=='string'||value.length>45||
     !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(value))
    return null;
  const valueMs=Date.parse(value);
  return Number.isFinite(valueMs)?new Date(valueMs).toISOString():null;
}
export function verifiedObservation(text){
  const lines=String(text).trim().split(/\r?\n/);
  if(lines.length!==2||text.length>100000)
    throw new Error('observation_format');
  const [scope,result]=lines.map(x=>JSON.parse(x));
  if(scope?.technical_source_scope?.supported!==13||
     scope.technical_source_scope.source_manifest!=='ingestion/source-specs.radar.json'||
     result?.schema_version!==1||result.status!=='review_ready'||
     result.mode!=='read_only'||result.manual_review_required!==true||
     result.register_authoritative!==true||
     result.application_submissions!==0||result.google_sheet_rows_written!==0||
     !Array.isArray(result.failures)||result.failures.length!==0||
     !Array.isArray(result.candidates)||result.candidates.length>MAX_CANDIDATES||
     result.counts?.review_candidates!==result.candidates.length)
    throw new Error('observation_not_accepted');
  return result.candidates;
}
export function registerIndex(valueRanges){
  if(!Array.isArray(valueRanges)||valueRanges.length!==8)
    throw new Error('register_ranges');
  const a=valueRanges.map(r=>r.values||[]);
  const headers=['vacancy_id','canonical_url','vacancy_id','status','application_url','event_id','event_type','status_after'];
  if(headers.some((x,i)=>a[i]?.[0]?.[0]!==x)||
     a[0]?.[0]?.[1]!=='status'||a[1]?.[0]?.[1]!=='official_url'||
     a[5]?.[0]?.[1]!=='vacancy_id')
    throw new Error('register_header_drift');
  const vmax=Math.max(a[0].length,a[1].length);
  const v=Array.from({length:vmax},(_,i)=>[
    String(a[0][i]?.[0]||''),String(a[0][i]?.[1]||''),'','','','',
    String(a[1][i]?.[0]||''),String(a[1][i]?.[1]||'')
  ]);
  const amax=Math.max(a[2].length,a[3].length,a[4].length);
  const apps=Array.from({length:amax},(_,i)=>[
    String(a[2][i]?.[0]||''),'',String(a[3][i]?.[0]||''),'',String(a[4][i]?.[0]||'')
  ]);
  const emax=Math.max(a[5].length,a[6].length,a[7].length);
  const events=Array.from({length:emax},(_,i)=>[
    String(a[5][i]?.[0]||''),String(a[5][i]?.[1]||''),'',
    String(a[6][i]?.[0]||''),'',String(a[7][i]?.[0]||'')
  ]);
  return buildRegisterIndex(v,apps,events);
}
export function selectFreshRows({candidates,index,existingIds,existingUrls,now,runId}){
  if(!Array.isArray(candidates)||candidates.length>MAX_CANDIDATES||
     !(existingIds instanceof Set)||!(existingUrls instanceof Set)||
     !Number.isSafeInteger(Date.parse(now))||!/^\d{5,30}$/.test(String(runId)))
    throw new Error('intake_input');
  const nowMs=Date.parse(now),rows=[];
  for(const c of candidates){
    if(!c||typeof c!=='object'||Array.isArray(c))throw new Error('candidate_type');
    const identity=String(c.observation_key||'');
    const parts=identity.split(':');
    const sourceId=String(c.source_id||'');
    const title=String(c.title||'');
    const url=String(c.official_url||'');
    if(parts.length!==3||parts[0]!==sourceId||!parts[1]||!parts[2]||
       identity.length>210||title.length>240||url.length>500||
       String(c.employer||'').length>160||String(c.location||'').length>160)
      throw new Error('candidate_contract');
    const job={identity,source_id:sourceId,source_account:parts[1],source_job_id:parts[2],
      title,url,source_url:url};
    if(!isValidJob(job)||strongRoleKeys(url).length===0)
      throw new Error('candidate_official_url');
    // The intake is strictly limited to the user's WordPress and automation families.
    if(!TITLE_FAMILY.test(title))continue;
    // The first-observed timestamp is not an official publication date.
    const published=utcDate(c.confirmed_published_at);
    if(!published)continue;
    const age=nowMs-Date.parse(published);
    if(age< -15*60*1000||age>MAX_AGE_MS)continue;
    if(existingIds.has(identity)||existingUrls.has(url))continue;
    const matched=matchRegister(job,index);
    if(matched.applied||matched.known)continue;
    const hash=createHash('sha256').update([identity,title,url,published].join('\n')).digest('hex');
    rows.push([
      identity,sourceId,parts[2],String(c.employer||''),title,url,url,
      String(c.remote_text||'').slice(0,160),String(c.location||'').slice(0,160),
      '',published,now,now,'geen_ingediende_sollicitatie_in_register',
      'officiele_ats_observatie_nog_te_verifieren','handmatige_nl_check',
      'voorselectie_nog_te_verifieren','controleer_officiele_vacature',
      'Publicatiedatum uit officieel ATS; volledige remote/NL, taal, geschiktheid en actuele status nog niet bevestigd.',
      hash,String(runId)
    ]);
    existingIds.add(identity);existingUrls.add(url);
  }
  return rows;
}
async function checkedFetch(url,options={}){
  const result=await fetch(url,{...options,redirect:'error',signal:AbortSignal.timeout(15000)});
  if(!result.ok)throw new Error('google_http_'+result.status);
  const raw=await result.text();
  if(raw.length>MAX_BYTES)throw new Error('google_response_too_large');
  return JSON.parse(raw);
}
async function token(env){
  const secret=JSON.parse(env.GOOGLE_SERVICE_ACCOUNT_JSON||'{}');
  if(secret.client_email!==env.RADAR_EXPECTED_SERVICE_ACCOUNT_EMAIL||
     secret.client_email!=='vacature-radar@leads-507621.iam.gserviceaccount.com'||
     !secret.private_key)throw new Error('service_account_mismatch');
  const now=Math.floor(Date.now()/1000);
  const encode=x=>Buffer.from(JSON.stringify(x)).toString('base64url');
  const jwt=encode({alg:'RS256',typ:'JWT'})+'.'+encode({
    iss:secret.client_email,scope:SCOPE,aud:'https://oauth2.googleapis.com/token',
    iat:now,exp:now+3000
  });
  const signature=sign('RSA-SHA256',Buffer.from(jwt),secret.private_key).toString('base64url');
  const reply=await checkedFetch('https://oauth2.googleapis.com/token',{
    method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:new URLSearchParams({grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion:jwt+'.'+signature})
  });
  if(typeof reply.access_token!=='string'||!reply.access_token)throw new Error('oauth_invalid');
  return reply.access_token;
}
async function ranges(id,names,key){
  const endpoint=new URL(API+id+'/values:batchGet');
  for(const range of names)endpoint.searchParams.append('ranges',range);
  const data=await checkedFetch(endpoint.toString(),{headers:{Authorization:'Bearer '+key}});
  if(!Array.isArray(data.valueRanges)||data.valueRanges.length!==names.length)
    throw new Error('sheets_ranges_invalid');
  return data.valueRanges;
}
async function verifyRows(key,expected,range){
  const data=await ranges(RESULT_SHEET_ID,[range],key);
  const actual=data[0].values||[];
  if(actual.length!==expected.length||expected.some((r,i)=>
    r.length!==21||actual[i]?.length!==21||r.some((value,k)=>actual[i][k]!==value)))
    throw new Error('intake_readback_mismatch');
}
export async function appendFresh({env,artifactText}){
  if(env.GITHUB_REPOSITORY!=='Yolol100/vacature-engine'||
     env.GITHUB_REF!=='refs/heads/main'||
     env.GITHUB_WORKFLOW!=='Vacature Radar quarter-hour observations'||
     env.RADAR_RESULT_ID!==RESULT_SHEET_ID||env.VACATURE_REGISTER_ID!==REGISTER_ID||
     (env.GITHUB_EVENT_NAME!=='schedule'&&
      !(env.GITHUB_ACTOR==='Yolol100'&&
        (env.GITHUB_EVENT_NAME==='workflow_dispatch'||
         (env.GITHUB_EVENT_NAME==='issues'&&
          env.RADAR_ISSUE_TITLE==='[radar] quarter 10')))))
    throw new Error('intake_unauthorized_context');
  const candidates=verifiedObservation(artifactText);
  const now=new Date().toISOString();
  const key=await token(env);
  const get=async(id,rs)=>ranges(id,rs,key);
  const [register,radar]=await Promise.all([
    get(REGISTER_ID,["'Vacatures'!A1:B","'Vacatures'!G1:H",
      "'Applications'!A1:A","'Applications'!C1:C","'Applications'!E1:E",
      "'ApplicationEvents'!A1:B","'ApplicationEvents'!D1:D","'ApplicationEvents'!F1:F"]),
    get(RESULT_SHEET_ID,["'Nieuwe vacatures'!A1:U1",
      "'Nieuwe vacatures'!A2:A10000","'Nieuwe vacatures'!F2:F10000"])
  ]);
  const header=radar[0].values?.[0];
  if(JSON.stringify(header)!==JSON.stringify(INTAKE_HEADERS))throw new Error('intake_header_drift');
  const already=new Set((radar[1].values||[]).map(r=>String(r[0]||'')).filter(Boolean));
  const urls=new Set((radar[2].values||[]).map(r=>String(r[0]||'')).filter(Boolean));
  const rows=selectFreshRows({candidates,index:registerIndex(register),
    existingIds:already,existingUrls:urls,now,runId:env.GITHUB_RUN_ID});
  if(rows.length===0)return {status:'no_new_verified_date_candidates',stored:0};
  const endpoint=new URL(API+RESULT_SHEET_ID+'/values/'+
    encodeURIComponent("'Nieuwe vacatures'!A:U")+':append');
  endpoint.searchParams.set('valueInputOption','RAW');
  endpoint.searchParams.set('insertDataOption','INSERT_ROWS');
  const data=await checkedFetch(endpoint.toString(),{
    method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},
    body:JSON.stringify({majorDimension:'ROWS',values:rows})
  });
  if(data.updates?.updatedRows!==rows.length||
     !/^'Nieuwe vacatures'!A\d+:U\d+$/.test(data.updates?.updatedRange||''))
    throw new Error('intake_append_unexpected_response');
  await verifyRows(key,rows,data.updates.updatedRange);
  return {status:'stored_pending_specialist_verification',stored:rows.length};
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===process.argv[1]){
  try{
    const text=readFileSync('.runtime/scheduled-observations.log','utf8');
    const receipt=await appendFresh({env:process.env,artifactText:text});
    console.log(JSON.stringify(receipt));
  }catch(error){
    // Do not log OAuth secrets, URLs, person records or upstream error bodies.
    console.error('radar_drive_intake_failed:'+(
      /^google_http_[45]\d\d$/.test(error?.message||'')?error.message:
      ['observation_format','observation_not_accepted','register_ranges',
       'register_header_drift','intake_input','candidate_type','candidate_contract',
       'candidate_official_url','service_account_mismatch','oauth_invalid',
       'sheets_ranges_invalid','intake_readback_mismatch','intake_unauthorized_context',
       'intake_header_drift','intake_append_unexpected_response','google_response_too_large']
       .includes(error?.message)?error.message:'internal_failure'));
    process.exitCode=1;
  }
}
