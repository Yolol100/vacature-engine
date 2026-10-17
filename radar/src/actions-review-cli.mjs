// One source of business truth (Vacature Register), one existing technical
// radar-state branch. The default execution is strictly read-only.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {reviewOnce,selectSupportedSources} from './actions-review.mjs';
import {parseReviewState,commitReviewReceipt} from './review-state.mjs';
import {readOnlyAccessToken,readRanges} from './google-sheets.mjs';
import {actionsPublicJobs,actionsPublicDiscoveryJobs} from './official-ats.mjs';
import {selectTieredSources} from './tiered-discovery.mjs';
import {safeDiagnosticError} from './health.mjs';

const env=process.env;
const event=env.GITHUB_EVENT_NAME;
const title=env.RADAR_ISSUE_TITLE||'';
const persist=env.RADAR_PERSIST==='1';
let maxCandidates=5;
let tiered=false;
if(event==='issues') {
  const match=/^\[radar\] (review|discover) (5|10)$/.exec(title);
  if(!match||persist) {
    console.error('Unauthorized radar issue command or write mode');
    process.exit(1);
  }
  maxCandidates=Number(match[2]);
  tiered=match[1]==='discover';
}else if(event==='workflow_dispatch') {
  maxCandidates=Number(env.RADAR_MAX_CANDIDATES||'5');
  tiered=env.RADAR_DISCOVERY_SCOPE==='tiered';
  if(!['','official_only','tiered'].includes(env.RADAR_DISCOVERY_SCOPE||''))
    throw new Error('Invalid manual discovery mode');
  if(persist&&tiered) {
    console.error('Discovery-only mode cannot write a technical checkpoint');
    process.exit(1);
  }
  if(persist&&env.RADAR_APPROVED_PERSIST!=='yes') {
    console.error('Radar persistent review not explicitly enabled');
    process.exit(1);
  }
}else{
  console.error('Unsupported radar event');
  process.exit(1);
}
const path='.runtime/review-observations.json';
try{
  // A missing or corrupt fetched history is NOT silently replaced.
  const prior=parseReviewState(readFileSync(path,'utf8'));
  // GitHub re-run preserves GITHUB_RUN_ID. A crash *after* the branch commit
  // must resume at the verified receipt, never re-fetch or rewrite candidates.
  if(persist && prior.runs.some(r=>r.run_id===String(env.GITHUB_RUN_ID))) {
    mkdirSync('.runtime',{recursive:true});
    writeFileSync('.runtime/review-observations.next.json',
      JSON.stringify(prior)+'\n',{flag:'wx',mode:0o600});
    console.log(JSON.stringify({status:'already_committed',mode:'technical_checkpoint',
      run_id:String(env.GITHUB_RUN_ID),google_sheet_rows_written:0,
      application_submissions:0,external_sources_polled:0}));
  }else {
  const manifest=JSON.parse(readFileSync('ingestion/source-specs.radar.json','utf8'));
  const {sources,unsupported,unverified}=selectSupportedSources(manifest);
  const tieredSources=tiered?selectTieredSources(JSON.parse(
    readFileSync('ingestion/source-specs.deploy.json','utf8'))):[];
  console.log(JSON.stringify({technical_source_scope:{
    supported:sources.length,unsupported:unsupported.length,
    unverified:unverified.length,
    source_manifest:'ingestion/source-specs.radar.json'}}));
  const result=await reviewOnce({env,accessToken:readOnlyAccessToken,readRanges,
    publicJobs:source=>actionsPublicJobs(source,{maxJobs:1000,maxBytes:6_000_000}),
    maxCandidates,priorState:prior,sources,unsupportedSources:unsupported,
    unverifiedSources:unverified,tieredSources,
    publicDiscoveryJobs:tiered?actionsPublicDiscoveryJobs:null});
  console.log(JSON.stringify(result));
  if(result.status!=='review_ready') {
    process.exitCode=1;
  }else if(persist) {
    const {state,added,already_committed}=commitReviewReceipt(prior,{
      runId:env.GITHUB_RUN_ID,result
    });
    mkdirSync('.runtime',{recursive:true});
    writeFileSync('.runtime/review-observations.next.json',JSON.stringify(state)+'\n',
      {flag:'wx',mode:0o600});
    console.log(JSON.stringify({checkpoint_staged:true,added,
      already_committed,persisted_runs:state.runs.length}));
  }
  }
}catch(error){
  // An OAuth JWT can be valid yet belong to an account that has no Google
  // Sheet permission. Report ONLY equality to the already-shared principal,
  // never the service-account JSON, email, private key or access token.
  if(String(error?.message||'').startsWith('Radar Sheets preflight failed')){
    let same=false;
    try{
      same=JSON.parse(env.GOOGLE_SERVICE_ACCOUNT_JSON||'{}').client_email===
        env.RADAR_EXPECTED_SERVICE_ACCOUNT_EMAIL;
    }catch{}
    console.error('radar_service_account_matches_existing_sheet_reader:'+same);
  }
  console.error('vacature_actions_review_failed:'+safeDiagnosticError(error));
  process.exitCode=1;
}
