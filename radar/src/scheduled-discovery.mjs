// Extra read-only discovery alongside the original 2-hour official ATS scan.
// Eight publicly documented API/RSS providers only; never an official vacancy
// verdict, never a business Sheets writer or a substitute for source coverage.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {readOnlyAccessToken,readRanges} from './google-sheets.mjs';
import {registerIndex} from './drive-intake.mjs';
import {selectTieredSources,orderTieredSources,collectTieredDiscovery} from './tiered-discovery.mjs';
import {actionsPublicDiscoveryJobs} from './official-ats.mjs';
import {pollWithRetry,preliminaryInterest,preliminaryRemoteEvidence,
  preliminaryNetherlandsScope} from './actions-review.mjs';
import {matchRegister,strongRoleKeys,canonicalUrl} from './logic.mjs';
import {safeDiagnosticError} from './health.mjs';

const REG='1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0';
const RAD='1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ';
const REGS=[
  "'Vacatures'!A1:B","'Vacatures'!G1:H",
  "'Applications'!A1:A","'Applications'!C1:C","'Applications'!E1:E",
  "'ApplicationEvents'!A1:B","'ApplicationEvents'!D1:D",
  "'ApplicationEvents'!F1:F"
];
const SOURCES=[
  "'Bronnen'!A1:A","'Bronnen'!C1:C","'Bronnen'!E1:E","'Bronnen'!M1:M"
];
const HISTORY=[
  "'Nieuwe vacatures'!A1:A","'Nieuwe vacatures'!F1:F",
  "'Radar State'!A1:A","'Radar State'!C1:C"
];
const EXPECTED_HEADERS=['source_id','source_type','priority','status'];
const HISTORY_HEADERS=['observation_key','officiele_url','identity','official_url'];
const RESULT='.runtime/scheduled-discovery.json';
function rows(x){return x?.values||[];}
export function authorizeDiscovery(env){
  const safeActor=env.GITHUB_ACTOR==='Yolol100'&&(
    env.GITHUB_EVENT_NAME==='workflow_dispatch'||
    (env.GITHUB_EVENT_NAME==='issues'&&env.RADAR_ISSUE_TITLE==='[radar] quarter 10'));
  if(env.GITHUB_REPOSITORY!=='Yolol100/vacature-engine'||
     env.GITHUB_REF!=='refs/heads/main'||
     env.GITHUB_WORKFLOW!=='Vacature Radar quarter-hour observations'||
     env.VACATURE_REGISTER_ID!==REG||env.RADAR_RESULT_ID!==RAD||
     !/^\d{6,24}$/.test(String(env.GITHUB_RUN_ID||''))||
     (env.GITHUB_EVENT_NAME!=='schedule'&&!safeActor)||
     env.RADAR_DISCOVERY_SCOPE!=='approved_feeds_readonly'||
     env.RADAR_PERSIST==='1')
    throw new Error('discovery_context_denied');
}
export function sourceIndex(sourceRanges){
  if(!Array.isArray(sourceRanges)||sourceRanges.length!==4||
     sourceRanges.some((r,i)=>r?.[0]?.[0]!==EXPECTED_HEADERS[i]))
    throw new Error('discovery_sources_schema');
  const [ids,types,prios,statuses]=sourceRanges;
  const map=new Map(),active=[];
  for(let i=1;i<ids.length;i++){
    const id=String(ids[i]?.[0]||'').trim();
    if(!id)continue;
    if(map.has(id))throw new Error('discovery_duplicate_source');
    const record={type:types[i]?.[0],priority:prios[i]?.[0],status:statuses[i]?.[0]};
    map.set(id,record);
    if(record.status==='active')active.push(id);
  }
  return {map,active};
}
export function seenKeys(radarRanges){
  if(!Array.isArray(radarRanges)||radarRanges.length!==4||
     radarRanges.some((r,i)=>r?.[0]?.[0]!==HISTORY_HEADERS[i]))
    throw new Error('discovery_history_schema');
  const ids=new Set(),roles=new Set();
  for(const table of [radarRanges[0],radarRanges[2]]){
    for(const r of table.slice(1)){
      const id=String(r?.[0]||'').trim();if(id)ids.add(id);
    }
  }
  for(const table of [radarRanges[1],radarRanges[3]]){
    for(const r of table.slice(1)){
      for(const key of strongRoleKeys(String(r?.[0]||'')))roles.add(key);
    }
  }
  return {ids,roles};
}
export async function runApprovedDiscovery({env,token,read,loadSpecs,fetchJobs}){
  authorizeDiscovery(env);
  const auth=await token(env);
  const [configRows,sourceRanges,registerRanges,historical]=await Promise.all([
    read(REG,["'Config'!A1:B"],auth),
    read(REG,SOURCES,auth),
    read(REG,REGS,auth),
    read(RAD,HISTORY,auth)
  ]);
  if(configRows?.length!==1||rows(configRows[0])[0]?.[0]!=='key'||
     rows(configRows[0])[0]?.[1]!=='value')
    throw new Error('discovery_config_schema');
  const config=new Map(rows(configRows[0]).slice(1).map(r=>[r[0],r[1]]));
  if(String(config.get('radar_enabled')).toUpperCase()!=='FALSE'||
     config.get('radar_delivery')!=='none')
    throw new Error('discovery_unexpected_radar_mode');
  if(sourceRanges?.length!==4||registerRanges?.length!==8||historical?.length!==4)
    throw new Error('discovery_ranges_incomplete');
  const registry=sourceIndex(sourceRanges.map(rows));
  const history=seenKeys(historical.map(rows));
  const index=registerIndex(registerRanges);
  const sourceSpecs=selectTieredSources(loadSpecs());
  const ordered=orderTieredSources(sourceSpecs,registry.map,config);
  const result=await collectTieredDiscovery({
    sources:ordered.enabled,skipped:ordered.skipped,maxCandidates:10,
    seenIds:history.ids,seenRoles:history.roles,register:index,
    fetchJobs,pollWithRetry,
    preliminaryInterest,preliminaryRemoteEvidence,preliminaryNetherlandsScope,
    matchRegister,strongRoleKeys,canonicalUrl,safeDiagnosticError,scanAll:true
  });
  return {
    schema_version:1,mode:'read_only_discovery_only',
    provider_contract_count:sourceSpecs.length,
    registered_active_source_entries:registry.active.length,
    checked_feeds:result.checked_sources,skipped_feeds:result.skipped_sources,
    unpolled_feeds:result.not_polled_sources,failures:result.failures,
    counts:result.counts,candidates:result.candidates,
    status:result.status,github_run_id:String(env.GITHUB_RUN_ID),
    google_sheet_rows_written:0,application_submissions:0,
    source_scope_note:'Only eight approved public API/RSS sources. All other active registry sources are NOT claimed as scanned. Official vacancy verification belongs to ChatGPT.'
  };
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===process.argv[1]){
  try{
    const result=await runApprovedDiscovery({
      env:process.env,token:readOnlyAccessToken,read:readRanges,
      loadSpecs:()=>JSON.parse(readFileSync('ingestion/source-specs.deploy.json','utf8')),
      fetchJobs:source=>actionsPublicDiscoveryJobs(source)
    });
    mkdirSync('.runtime',{recursive:true});
    writeFileSync(RESULT,JSON.stringify(result)+'\n',{mode:0o600,flag:'wx'});
    console.log(JSON.stringify({
      mode:result.mode,status:result.status,
      registered_active_source_entries:result.registered_active_source_entries,
      configured_feeds:result.provider_contract_count,
      checked_feeds:result.checked_feeds.length,
      unverified_leads:result.candidates.length,
      failures:result.failures.map(x=>({source:x.source,reason:x.reason})),
      google_sheet_rows_written:0,application_submissions:0
    }));
    if(result.status!=='review_ready')process.exitCode=1;
  }catch(error){
    // Never leak Sheets, credentials, source payloads, or external error bodies.
    const known=new Set(['discovery_context_denied','discovery_sources_schema',
      'discovery_duplicate_source','discovery_history_schema',
      'discovery_config_schema','discovery_unexpected_radar_mode',
      'discovery_ranges_incomplete']);
    console.error('scheduled_discovery_failed:'+(
      known.has(error?.message)?error.message:'unverified_provider_or_access'));
    process.exitCode=1;
  }
}
