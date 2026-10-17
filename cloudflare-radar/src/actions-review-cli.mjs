// Only owner-authored issue commands or explicit workflow dispatch may invoke a read-only run.
import {reviewOnce} from './actions-review.mjs';
import {accessToken,readRanges} from './google-sheets.mjs';
import {publicJobs} from './official-ats.mjs';
import {safeDiagnosticError} from './health.mjs';

const env=process.env;
const title=env.RADAR_ISSUE_TITLE||'';
let maxCandidates=5;
if(env.GITHUB_EVENT_NAME==='issues') {
  const match=/^\[radar\] review (5|10)$/.exec(title);
  if(!match) {console.error('Unauthorized radar issue command');process.exit(1);}
  maxCandidates=Number(match[1]);
} else if(env.GITHUB_EVENT_NAME==='workflow_dispatch') {
  maxCandidates=Number(env.RADAR_MAX_CANDIDATES||'5');
} else {
  console.error('Unsupported execution event');
  process.exit(1);
}
try {
  const result=await reviewOnce({env,accessToken,readRanges,publicJobs,maxCandidates});
  // The Actions log is public: redact unpublished/private Google register rows and OAuth state.
  console.log(JSON.stringify(result));
  if(result.status!=='review_ready')process.exitCode=1;
} catch(error) {
  console.error('vacature_actions_review_failed:'+safeDiagnosticError(error));
  process.exitCode=1;
}
