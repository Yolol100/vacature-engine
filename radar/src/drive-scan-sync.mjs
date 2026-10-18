// Persist bounded GitHub scan evidence in EXISTING Google Sheets tabs only.
// The canonical Register owns sources and applications. Google Radar is technical evidence.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {token,ranges,checkedFetch} from './drive-intake.mjs';
import {canonicalUrl,strongRoleKeys} from './logic.mjs';
import {safeSourceUrl} from './source-sweep.mjs';

const REG='1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0';
const RAD='1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ';
const BASE='https://sheets.googleapis.com/v4/spreadsheets/';
const COVER_HEAD=['bron_id','bronnaam','brontype','prioriteit','registratiestatus',
  'bron_url','controlekanaal','laatst_bezocht_utc','resultaat','bewijs_url','laatste_run_id','opmerkingen'];
const LEAD_HEAD=['vondst_id','bron_id','brontype','bron_naam','functietitel','gevonden_url',
  'bron_url','publicatiedatum_uit_bron','eerste_ontdekt_utc','status','extractiemethode',
  'run_id','opmerkingen','content_hash'];
const RUN_HEAD=['run_id','gestart_utc','afgerond_utc','bronnen_gecontroleerd',
  'observaties','nieuwe_records','bekende_records','historische_sollicitaties',
  'overgeslagen','fouten','status','opmerkingen'];
const FEEDS=new Set(['remotive','jobicy-api','himalayas','we-work-remotely',
  'remote-ok','remote-landers-api','remotejobs-org','arbeitnow-api']);
const requireHeader=(matrix,header,label)=>{
  if(JSON.stringify(matrix?.[0])!==JSON.stringify(header))throw Error(label+'_schema_drift');
};
function validRun(run){return /^\d{6,24}$/.test(String(run||''));}
function assertOrigin(env){
  const owner=env.GITHUB_ACTOR==='Yolol100'&&
    (env.GITHUB_EVENT_NAME==='workflow_dispatch'||
     (env.GITHUB_EVENT_NAME==='issues'&&env.RADAR_ISSUE_TITLE==='[radar] quarter 10'));
  if(env.GITHUB_REPOSITORY!=='Yolol100/vacature-engine'||
    env.GITHUB_REF!=='refs/heads/main'||
    env.GITHUB_WORKFLOW!=='Vacature Radar quarter-hour observations'||
    env.VACATURE_REGISTER_ID!==REG||env.RADAR_RESULT_ID!==RAD||
    !validRun(env.GITHUB_RUN_ID)||(env.GITHUB_EVENT_NAME!=='schedule'&&!owner))
    throw Error('scan_sync_unauthorized');
}
export function mergeCoverage(register,coverage,sweep,runId){
  if(!Array.isArray(register)||!Array.isArray(coverage)||
    register.length<2||register.length>350||register.length!==coverage.length||
    register[0]?.[0]!=='source_id'||register[0]?.[12]!=='status')
    throw Error('scan_source_schema');
  requireHeader(coverage,COVER_HEAD,'scan_coverage');
  if(sweep?.schema_version!==1||
    sweep?.mode!=='public_surface_audit_not_vacancy_enumeration'||
    sweep?.run_id!==String(runId)||!Array.isArray(sweep?.source_statuses)||
    sweep.source_statuses.length>350||
    sweep?.attempted!==sweep.source_statuses.length||
    sweep?.registered_active!==sweep.attempted||
    sweep?.official_job_matches_verified!==0)
    throw Error('scan_artifact_schema');
  const active=new Map(),ids=new Set();
  for(let i=1;i<register.length;i++){
    const r=register[i],c=coverage[i],id=String(r[0]||'');
    if(!id||ids.has(id)||c?.[0]!==id||c?.[1]!==r[1]||
      c?.[2]!==r[2]||c?.[3]!==r[4]||c?.[4]!==r[12]||
      c?.[5]!==r[3])
      throw Error('scan_coverage_register_drift');
    ids.add(id);
    if(r[12]==='active')active.set(id,i);
  }
  if(active.size!==sweep.attempted)throw Error('scan_active_count_drift');
  const output=coverage.slice(1).map(r=>[7,8,9,10].map(i=>String(r[i]||'')));
  const seen=new Set();
  for(const p of sweep.source_statuses){
    if(!p||!active.has(p.source_id)||seen.has(p.source_id)||
      typeof p.status!=='string'||p.status.length>85||
      !['public_surface_reachable_not_vacancies_verified',
        'redirect_requires_official_verification','access_limited','http_failure',
        'network_timeout_or_blocked','unsupported_or_unsafe_url',
        'public_vacancy_link_discovery_unverified'].includes(p.status))
      throw Error('scan_status_invalid');
    seen.add(p.source_id);
    const iso=new Date(p.checked_at);
    if(!Number.isFinite(iso.valueOf())||Math.abs(Date.now()-iso.valueOf())>2*3600000)
      throw Error('scan_timestamp_invalid');
    const link=p.evidence_url?safeSourceUrl(p.evidence_url):null;
    if(p.evidence_url&&!link)throw Error('scan_url_invalid');
    output[active.get(p.source_id)-1]=[iso.toISOString(),p.status,link||'',String(runId)];
  }
  return output;
}
const urlKeys=u=>{
  const x=canonicalUrl(u);
  return x?[x,...strongRoleKeys(x)]:[];
};
export function selectDiscoveryRows(discovery,existing,now,runId){
  if(discovery===null)return [];
  if(discovery?.schema_version!==1||discovery?.mode!=='read_only_discovery_only'||
    discovery?.github_run_id!==String(runId)||
    discovery?.google_sheet_rows_written!==0||discovery?.application_submissions!==0||
    !Array.isArray(discovery.candidates)||discovery.candidates.length>10)
    throw Error('discovery_receipt_invalid');
  const seenIds=new Set(existing.ids),seenKeys=new Set(existing.urls.flatMap(urlKeys));
  const out=[];
  for(const c of discovery.candidates){
    const id=String(c?.observation_key||''),u=String(c?.discovery_url||''),
      source=String(c?.source_id||''),title=String(c?.title||'');
    if(!FEEDS.has(source)||!id.startsWith(source+':')||
      id.length>800||title.length<3||title.length>240||
      !safeSourceUrl(u)||!canonicalUrl(u))
      throw Error('discovery_candidate_invalid');
    const keys=urlKeys(u);
    if(seenIds.has(id)||keys.some(k=>seenKeys.has(k)))continue;
    const hash=createHash('sha256').update(id+'\n'+canonicalUrl(u)).digest('hex');
    out.push([id,source,'public_api_rss_discovery',
      String(c.employer||'').slice(0,160),title,canonicalUrl(u),
      safeSourceUrl(String(c.source_url||''))||'','',now,
      'onbevestigde_feed_vondst','approved_feed_readonly',String(runId),
      'Alleen vondst. Controleer werkgevers-/ATS-detailpagina, echte publicatiedatum, NL-remote, taal en sollicitatiehistorie.',hash]);
    seenIds.add(id);
    for(const k of keys)seenKeys.add(k);
  }
  return out;
}

export function selectPublicClueRows(sweep,existing,now,runId){
  if(!Array.isArray(sweep?.source_statuses))throw Error('public_clues_schema');
  const knownIds=new Set(existing.ids),knownUrls=new Set(existing.urls.flatMap(urlKeys));
  const rows=[];
  for(const source of sweep.source_statuses){
    const clues=source.jobposting_discoveries||[];
    if(!Array.isArray(clues)||clues.length>3||
      clues.length>0&&source.status!=='public_vacancy_link_discovery_unverified')
      throw Error('public_clues_contract');
    for(const clue of clues){
      const url=String(clue.url||''),canon=canonicalUrl(url),keys=urlKeys(url);
      const sourceURL=String(source.evidence_url||'');
      if(!safeSourceUrl(url)||!safeSourceUrl(sourceURL)||
        new URL(url).hostname!==new URL(sourceURL).hostname||
        !['onsite_public_job_link','json_ld_jobposting'].includes(clue.method)||
        !canon||String(clue.title||'').length<8||String(clue.title||'').length>200)
        throw Error('public_clue_invalid');
      const id='web:'+source.source_id+':'+
        createHash('sha256').update(canon).digest('hex').slice(0,24);
      if(knownIds.has(id)||keys.some(k=>knownUrls.has(k)))continue;
      if(rows.length>=75)break;
      rows.push([id,String(source.source_id),'openbare_werkgever_of_carrierepagina',
        String(source.source_id),String(clue.title),canon,sourceURL,
        String(clue.source_date_hint||'').slice(0,40),now,
        'onbevestigde_bronvondst',clue.method,String(runId),
        'Openbare bronhint; publicatiedatum, exacte werkgeversvacature, remote NL, taal en sollicitatiehistorie nog inhoudelijk verifiëren.',
        createHash('sha256').update(id+'\n'+canon).digest('hex')]);
      knownIds.add(id);for(const k of keys)knownUrls.add(k);
    }
  }
  return rows;
}

async function writeValues(key,range,values,append=false){
  const path=append?'/values/'+encodeURIComponent(range)+':append':'/values:batchUpdate';
  const endpoint=new URL(BASE+RAD+path);
  if(append){endpoint.searchParams.set('valueInputOption','RAW');
    endpoint.searchParams.set('insertDataOption','INSERT_ROWS');}
  const body=append?{majorDimension:'ROWS',values}:
    {valueInputOption:'RAW',data:[{range,majorDimension:'ROWS',values}]};
  const result=await checkedFetch(endpoint.toString(),{
    method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},
    body:JSON.stringify(body)
  });
  if(append&&result.updates?.updatedRows!==values.length||
    !append&&result.totalUpdatedRows!==values.length)
    throw Error('scan_write_rowcount_mismatch');
  return append?result.updates.updatedRange:range;
}
async function verify(key,range,rows){
  const d=await ranges(RAD,[range],key);
  const a=d[0].values||[];
  if(a.length!==rows.length||a.some((r,i)=>
    rows[i].some((v,j)=>String(r[j]||'')!==String(v||''))))
    throw Error('scan_write_readback_mismatch');
}
async function appendUnique(key,range,rows){
  if(!rows.length)return 0;
  const written=await writeValues(key,range,rows,true);
  await verify(key,written,rows);
  return rows.length;
}
export async function syncDrive({env,sweep,discovery,now=new Date().toISOString()}){
  assertOrigin(env);
  const key=await token(env);
  const [r,c,leads,rv,lv,history,runs]=await Promise.all([
    ranges(REG,["'Bronnen'!A1:M350"],key),
    ranges(RAD,["'Brondekking'!A1:L500"],key),
    ranges(RAD,["'Bronvondsten'!A1:N10000"],key),
    ranges(REG,["'Vacatures'!G1:H2000"],key),
    ranges(RAD,["'Nieuwe vacatures'!A1:F10000"],key),
    ranges(RAD,["'Toonhistorie'!A1:B10000"],key),
    ranges(RAD,["'Runs'!A1:L1000"],key)
  ]);
  const register=r[0].values||[],coverage=c[0].values||[],found=leads[0].values||[],
    vac=rv[0].values||[],intake=lv[0].values||[],shown=history[0].values||[],
    runRows=runs[0].values||[];
  requireHeader(found,LEAD_HEAD,'scan_leads');
  requireHeader(runRows,RUN_HEAD,'scan_runs');
  if(vac[0]?.[0]!=='canonical_url'||vac[0]?.[1]!=='official_url'||
    intake[0]?.[0]!=='observation_key'||intake[0]?.[5]!=='officiele_url'||
    shown[0]?.[0]!=='vacature_identity'||shown[0]?.[1]!=='officiele_url')
    throw Error('scan_history_schema');
  const merged=mergeCoverage(register,coverage,sweep,env.GITHUB_RUN_ID);
  const identities=[...found.slice(1).map(x=>x[0]),...intake.slice(1).map(x=>x[0]),
    ...shown.slice(1).map(x=>x[0])].filter(Boolean);
  const knownUrls=[...found.slice(1).map(x=>x[5]),
    ...vac.slice(1).flatMap(x=>x.slice(0,2)),
    ...intake.slice(1).map(x=>x[5]),...shown.slice(1).map(x=>x[1])].filter(Boolean);
  const feedRows=selectDiscoveryRows(discovery,{ids:identities,urls:knownUrls},
    now,env.GITHUB_RUN_ID);
  const publicRows=selectPublicClueRows(sweep,{
    ids:[...identities,...feedRows.map(row=>row[0])],
    urls:[...knownUrls,...feedRows.map(row=>row[5])]
  },now,env.GITHUB_RUN_ID);
  const toAppend=[...feedRows,...publicRows];
  const coveredRange="'Brondekking'!H2:K"+coverage.length;
  await writeValues(key,coveredRange,merged);
  await verify(key,coveredRange,merged);
  const leadCount=await appendUnique(key,"'Bronvondsten'!A:N",toAppend);
  const knownRun=runRows.slice(1).some(x=>String(x[0])===String(env.GITHUB_RUN_ID));
  let runCount=0;
  if(!knownRun){
    const counts=sweep.counts||{};
    const errors=Object.entries(counts).filter(([k])=>k!=='public_surface_reachable_not_vacancies_verified')
      .map(([k,v])=>k+':'+v).join('; ').slice(0,380);
    const row=[String(env.GITHUB_RUN_ID),now,now,
      String(sweep.attempted)+' publieke URL-pogingen',
      String(sweep.attempted)+' bereikbaarheidspogingen; geen complete vacature-enumeratie',
      String(leadCount)+' onbevestigde bronvondsten',
      '', 'Register alleen gelezen','',errors,
      'technisch_bewijs_opgeslagen',
      'GitHub '+env.GITHUB_EVENT_NAME+'-run; publieke URL-response != vacaturecontrole. '+
      'ATS + feeds staan apart in GitHub-artifacts. https://github.com/Yolol100/vacature-engine/actions/runs/'+env.GITHUB_RUN_ID];
    runCount=await appendUnique(key,"'Runs'!A:L",[row]);
  }
  return {status:'evidence_saved_in_existing_sheets',source_rows:merged.length,
    new_unverified_leads:leadCount,run_receipts_written:runCount,
    canonical_register_rows_written:0,applications_sent:0};
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===process.argv[1]){
  try{
    const sweep=JSON.parse(readFileSync('.runtime/source-sweep.json','utf8'));
    let discovery=null;try{discovery=JSON.parse(readFileSync('.runtime/scheduled-discovery.json','utf8'))}
    catch(e){if(e.code!=='ENOENT')throw e;}
    const result=await syncDrive({env:process.env,sweep,discovery});
    mkdirSync('.runtime',{recursive:true});
    writeFileSync('.runtime/sheet-sync-receipt.json',JSON.stringify(result)+'\n',{mode:0o600,flag:'wx'});
    console.log(JSON.stringify(result));
  }catch(error){
    const allowed=/^(?:scan_[a-z_]+|discovery_[a-z_]+|google_http_[45]\d\d)$/;
    console.error('drive_scan_sync_failed:'+
      (allowed.test(error?.message||'')?error.message:'internal_or_permission_error'));
    process.exitCode=1;
  }
}
