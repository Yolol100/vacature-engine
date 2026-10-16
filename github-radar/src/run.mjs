// Manual GitHub Actions CLI. No Cloudflare bindings, D1, cron or mutations.
import {writeFile,mkdir,appendFile} from 'node:fs/promises';
import {join} from 'node:path';
import {accessToken,readRanges} from './google.mjs';
import {publicJobs} from './ats.mjs';
import {PILOT_SOURCES,activeSourcePairs} from './logic.mjs';
import {REGISTER_COMPACT_RANGES,expandRegisterRanges} from './compact-register.mjs';
import {RADAR_RANGES,assessRadar} from './core.mjs';

const modes=new Set(['audit','review']);
export async function runRadar({env=process.env,read=readRanges,token=accessToken,ats=publicJobs,
  clock=()=>new Date().toISOString(),write=writeFile}={}){
  const mode=env.RADAR_MODE||'audit';
  if(!modes.has(mode))throw new Error('Invalid manual mode; audit or review only');
  // Fail BEFORE network traffic. A missing GitHub secret must never be
  // confused with a green or empty radar run.
  if(!env.GOOGLE_SERVICE_ACCOUNT_JSON)
    throw new Error('Missing GitHub Actions secret: VACATURE_RADAR_GOOGLE_SERVICE_ACCOUNT_JSON');
  if(!env.VACATURE_REGISTER_ID||!env.RADAR_RESULT_ID)
    throw new Error('Missing Google spreadsheet IDs');
  const auth=await token(env);
  const compact=await read(env.VACATURE_REGISTER_ID,REGISTER_COMPACT_RANGES,auth);
  const register=expandRegisterRanges(compact);
  const sources=register[0];
  if(sources?.[0]?.[0]!=='source_id'||sources[0][12]!=='status')
    throw new Error('Live source register header mismatch');
  const active=activeSourcePairs(sources,PILOT_SOURCES);
  if(!active.length)throw new Error('No active registered source pair');
  // Read historical baseline and radar output in one transport call. An
  // incomplete API response fails closed before any official ATS fetch.
  const [identityRows,urlRows,stateRows]=await read(env.RADAR_RESULT_ID,[
    ...RADAR_RANGES,"'Radar State'!A1:E"
  ],auth);
  if(stateRows?.[0]?.[0]!=='identity')throw new Error('Radar State not migrated');
  const fetched=[];
  for(const source of active){
    const jobs=await ats(source);
    fetched.push({instance:source.source_id+':'+source.account,jobs});
  }
  const report=assessRadar({register,radarValues:[identityRows,urlRows],
    stateRows,sourceJobs:fetched,generatedAt:clock()});
  if(mode==='audit')report.candidates=[];
  const base=env.RADAR_REPORT_DIR||'github-radar/output';
  await mkdir(base,{recursive:true});
  await write(join(base,'report.json'),JSON.stringify(report,null,2)+'\n',{mode:0o600});
  const summary=[
    '## Vacature Radar — GitHub Actions',
    '',
    '- Mode: '+mode+' (manual, review-only)',
    '- Official ATS sources: '+report.metrics.sources,
    '- Official roles checked: '+report.metrics.official_jobs,
    '- Already known baseline: '+report.metrics.baseline,
    '- Previously applied: '+report.metrics.previously_applied,
    '- Existing register or radar: '+report.metrics.already_known,
    '- For manual review: '+report.metrics.requires_manual_review,
    '- Google Sheets writes: **0**',
    '- Applications submitted: **0**',
    '',
    '**No final job recommendations without human/owner verification.**'
  ].join('\n')+'\n';
  await write(join(base,'summary.md'),summary,{mode:0o600});
  if(env.GITHUB_STEP_SUMMARY)await appendFile(env.GITHUB_STEP_SUMMARY,summary);
  return report;
}
if(process.argv[1]&&new URL('file://'+process.argv[1]).pathname===new URL(import.meta.url).pathname){
  runRadar().then(result=>console.log(JSON.stringify({
    status:'review_complete',sources:result.metrics.sources,
    checked:result.metrics.official_jobs,needs_review:result.metrics.requires_manual_review
  }))).catch(error=>{
    // Print only trusted locally-authored error, never response bodies/tokens.
    const message=String(error?.message||'Runner failed').slice(0,160);
    console.error('RADAR_ABORTED: '+message);
    process.exitCode=1;
  });
}
