// Best-effort, bounded public home/listing surface audit for every active source.
// A successful HTTP response does NOT prove that vacancies were enumerated.
// No login, browser anti-bot evasion, private pages, or inferred publication dates.
import {writeFileSync,mkdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {readOnlyAccessToken,readRanges} from './google-sheets.mjs';

const REG='1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0';
const HEAD=['source_id','source_name','source_type','base_url','priority','access_mode'];
const SAFE_TYPES=new Set(['job_board','discovery','discovery_api','ats','employer_direct',
  'wordpress_discovery','wordpress_directory']);
const BLOCKED_HOSTS=/^(?:localhost|127\.|0\.|10\.|192\.168\.|169\.254\.|172\.(?:1[6-9]|2[0-9]|3[01])\.|::1|metadata\.google\.internal)$/i;
export function safeSourceUrl(input){
  if(typeof input!=='string'||input.length>800) return null;
  let url;try{url=new URL(input)}catch{return null}
  if(url.protocol!=='https:'||url.username||url.password||url.port||
     !url.hostname.includes('.')||BLOCKED_HOSTS.test(url.hostname)||
     /\.(?:local|internal|test|invalid|localhost)$/i.test(url.hostname)||
     /^(?:\d{1,3}\.){3}\d{1,3}$/.test(url.hostname))return null;
  url.hash='';return url.toString();
}
export function activeRegistry(rows){
  if(!Array.isArray(rows)||rows.length<2||HEAD.some((x,i)=>rows[0]?.[i]!==x)||
    rows[0]?.[12]!=='status'||rows.length>500)throw Error('registry_drift');
  const seen=new Set(),output=[];
  for(const r of rows.slice(1)){
    const id=String(r[0]||'');
    if(!id||seen.has(id))throw Error('duplicate_or_missing_source_id');
    seen.add(id);
    if(r[12]!=='active')continue;
    output.push({id,name:String(r[1]||'').slice(0,100),
      type:String(r[2]||''),url:safeSourceUrl(r[3]),
      priority:String(r[4]||''),access:String(r[5]||'')});
  }
  return output;
}

// Parse only bounded public HTML; retain at most three UNVERIFIED employer-page
// clues per source. No JavaScript execution, secondary crawls or date inference.
const MAX_HTML=384000;
const FAMILY=/\b(?:wordpress|woo(?:\s|-)commerce|elementor|gutenberg|acf|n8n|zapier|make\.com|workflow automation|ai automation|process automation|automation specialist)\b/i;
const JOB_PATH=/(?:\/(?:jobs?|careers?|positions|vacancies|openings|apply|job-details?)\/|\/remote-jobs?\/)/i;
function publicRoleUrl(url,base){
  try{
    const absolute=new URL(url,base);
    if(absolute.hostname!==new URL(base).hostname)return null;
    return safeSourceUrl(absolute.href);
  }catch{return null;}
}
export function extractPublicRoleClues(html,base){
  if(typeof html!=='string'||html.length>MAX_HTML||!safeSourceUrl(base))return [];
  const result=[],seen=new Set();
  const add=(title,url,published,kind)=>{
    if(result.length>=3)return;
    const cleaned=String(title||'').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim().slice(0,200);
    const link=publicRoleUrl(String(url||''),base);
    if(!FAMILY.test(cleaned)||cleaned.length<8||!link||
       !JOB_PATH.test(new URL(link).pathname)||seen.has(link))return;
    seen.add(link);
    result.push({title:cleaned,url:link,source_url:base,
      source_date_hint:/^20\d{2}-\d\d-\d\d(?:$|T)/.test(String(published||''))?
        String(published).slice(0,40):'',method:kind});
  };
  for(const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)){
    if(result.length>=3)break;
    if(!/\btype\s*=\s*["']application\/ld\+json["']/i.test(m[1]))continue;
    if(m[2].length>100000)continue;
    let data;try{data=JSON.parse(m[2])}catch{continue}
    const queue=[data];let visited=0;
    while(queue.length&&visited++<70&&result.length<3){
      const node=queue.shift();
      if(Array.isArray(node)){queue.push(...node.slice(0,30));continue;}
      if(!node||typeof node!=='object')continue;
      const types=Array.isArray(node['@type'])?node['@type']:[node['@type']];
      if(types.some(t=>typeof t==='string'&&/(^|\/)JobPosting$/i.test(t)))
        add(node.title,node.url||node.mainEntityOfPage?.['@id'],node.datePosted,'json_ld_jobposting');
      if(Array.isArray(node['@graph']))queue.push(...node['@graph'].slice(0,30));
      if(Array.isArray(node.itemListElement))queue.push(...node.itemListElement.slice(0,30));
    }
  }
  if(result.length<3){
    let inspected=0;
    for(const m of html.matchAll(/<a\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*>([\s\S]*?)<\/a\s*>/gi)){
      if(++inspected>1400||result.length>=3)break;
      add(m[2],m[1],'','onsite_public_job_link');
    }
  }
  return result;
}
async function readBoundedPublicText(response){
  if(typeof response.body?.getReader==='function'){
    const reader=response.body.getReader(),decoder=new TextDecoder();
    let result='',count=0;
    try{
      while(true){
        const {done,value}=await reader.read();
        if(done)break;
        count+=value.length;
        if(count>MAX_HTML)break;
        result+=decoder.decode(value,{stream:true});
      }
    }finally{await reader.cancel().catch(()=>{});}
    return result;
  }
  if(typeof response.text==='function'){
    const text=await response.text();
    return text.length<=MAX_HTML?text:'';
  }
  if(typeof response.body?.cancel==='function')await response.body.cancel();
  return '';
}

export async function inspectSource(source,{request=fetch}={}){
  const now=new Date().toISOString();
  if(!SAFE_TYPES.has(source.type)||!source.url)return {
    source_id:source.id,checked_at:now,status:'unsupported_or_unsafe_url',
    evidence_url:'',http_status:null,job_count:null
  };
  // No redirects, no external code executed, no robots/captcha bypass.
  const url=source.url;
  try{
    const response=await request(url,{
      method:'GET',redirect:'manual',
      headers:{'User-Agent':'WebactueelVacatureRadar/1.0 (public source audit; contact via repository)',
        'Accept':'text/html,application/json,application/xml,text/xml,application/rss+xml,text/plain'},
      signal:AbortSignal.timeout(8500)
    });
    const code=response.status;
    let clues=[];
    if(code>=200&&code<300){
      const mime=String(response.headers?.get?.('content-type')||'');
      // MIME-less responses may be tested, but binary/video content is discarded.
      if(!mime||/html|text\/plain/i.test(mime)){
        const text=await readBoundedPublicText(response);
        clues=extractPublicRoleClues(text,url);
      }else if(response.body)await response.body.cancel();
    }else if(response.body)await response.body.cancel();
    return {source_id:source.id,checked_at:now,status:code>=200&&code<300?
      (clues.length?'public_vacancy_link_discovery_unverified':
        'public_surface_reachable_not_vacancies_verified'):
      code>=300&&code<400?'redirect_requires_official_verification':
      code===401||code===403||code===429?'access_limited':
      'http_failure',http_status:code,evidence_url:url,job_count:null,
      jobposting_discoveries:clues};
  }catch{
    return {source_id:source.id,checked_at:now,status:'network_timeout_or_blocked',
      evidence_url:url,http_status:null,job_count:null};
  }
}
export async function auditAll(sources,{inspect=inspectSource,concurrency=8}={}){
  if(!Array.isArray(sources)||sources.length>350||concurrency<1||concurrency>10)
    throw Error('source_audit_bound');
  const output=Array(sources.length),next={i:0};
  await Promise.all(Array.from({length:Math.min(concurrency,sources.length)},async()=>{
    while(next.i<sources.length){const at=next.i++;output[at]=await inspect(sources[at]);}
  }));
  return output;
}
async function run(){
  const env=process.env;
  if(env.GITHUB_REPOSITORY!=='Yolol100/vacature-engine'||
     env.GITHUB_REF!=='refs/heads/main'||
     env.GITHUB_WORKFLOW!=='Vacature Radar quarter-hour observations'||
     !['schedule','issues','workflow_dispatch'].includes(env.GITHUB_EVENT_NAME)||
     (env.GITHUB_EVENT_NAME!=='schedule'&&env.GITHUB_ACTOR!=='Yolol100'))
    throw Error('invalid_audit_context');
  const token=await readOnlyAccessToken(env);
  const sourceRanges=await readRanges(REG,["'Bronnen'!A1:O350"],token);
  const sources=activeRegistry(sourceRanges[0]);
  const observations=await auditAll(sources);
  const counts=observations.reduce((a,r)=>(a[r.status]=(a[r.status]||0)+1,a),{});
  const result={schema_version:1,mode:'public_surface_audit_not_vacancy_enumeration',
    run_id:String(env.GITHUB_RUN_ID),started_by:env.GITHUB_EVENT_NAME,
    registered_active:sources.length,attempted:observations.length,
    counts,source_statuses:observations,official_job_matches_verified:0,
    note:'A URL check does not prove complete job-board coverage, publication dates, or Netherlands eligibility. Only existing ATS and feed lanes find candidate jobs.'};
  mkdirSync('.runtime',{recursive:true});
  writeFileSync('.runtime/source-sweep.json',JSON.stringify(result)+'\n',{flag:'wx',mode:0o600});
  console.log(JSON.stringify({mode:result.mode,attempted:result.attempted,counts,
    official_job_matches_verified:0,google_sheet_rows_written:0}));
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===process.argv[1]){
  try{await run()}catch(e){console.error('source_sweep_failed:'+String(e.message).replace(/[^a-z0-9_]/gi,'').slice(0,50));process.exitCode=1;}
}
