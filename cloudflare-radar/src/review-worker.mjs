// Single active Worker entrypoint. Review-only, existing Cron and existing D1.
// Legacy deliver/reconcile helpers stay available for regression tests but are
// NOT imported or bundled into this scheduled entrypoint.
import {accessToken,readRanges} from './google-sheets.mjs';
import {publicJobs,existingKeys} from './official-ats.mjs';
import {runStagedReview} from './staged-review.mjs';
import {safeDiagnosticError} from './health.mjs';

export default{
  async scheduled(_event,env,ctx){
    // Double gate: neither a single flag nor the legacy delivery path can activate this review.
    // This initial staged path is review-only: no Google Sheets or applicant writes.
    if(env.RADAR_ENABLED!=='1'||env.RADAR_PIPELINE_MODE!=='staged_review')return;
    const ops={accessToken,readRanges,publicJobs,existingKeys,pagedVacancy:true,splitBootstrap:true};
    // The review-only stage engine already persists bounded checkpoint/error receipts.
    // Avoid multiple redundant D1 health writes on every Free-tier Cron invocation.
    ctx.waitUntil(runStagedReview(env,ops).then(outcome=>{
      console.log(JSON.stringify(outcome));
    }).catch(error=>{
      console.error('vacature_radar_staged_failed:'+safeDiagnosticError(error));
      throw error;
    }));
  },
  async fetch(){return new Response('Not found',{status:404});}
};

