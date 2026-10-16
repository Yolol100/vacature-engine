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
    // TEMPORARY DIAGNOSTIC ONLY: both production gates remain disabled.
    // Bound to one private D1 lease <= 18 minutes, no public HTTP trigger.
    if(env.RADAR_CPU_CANARY==='1'&&env.RADAR_ENABLED==='0'&&
       env.RADAR_PIPELINE_MODE==='off'&&env.RADAR_DB){
      const item=await env.RADAR_DB.prepare('SELECT value FROM radar_metadata WHERE name=?')
        .bind('micro:v2:cpu_canary').first();
      let permit;
      try{permit=JSON.parse(item?.value||'null');}catch{permit=null;}
      const now=Date.now();
      if(permit?.kind==='lean-bundle-cpu-20261016'&&
         Number.isSafeInteger(permit.started)&&Number.isSafeInteger(permit.until)&&
         permit.started<=now&&now<permit.until&&
         permit.until-permit.started<=18*60000){
        const testEnv={...env,RADAR_ENABLED:'1',RADAR_PIPELINE_MODE:'staged_review'};
        const ops={accessToken,readRanges,publicJobs,existingKeys,
          pagedVacancy:true,splitBootstrap:true};
        ctx.waitUntil(runStagedReview(testEnv,ops).then(outcome=>{
          console.log(JSON.stringify({private_cpu_audit:true,status:outcome.status,
            phase:outcome.phase||null}));
        }).catch(error=>{
          console.error('private_cpu_audit_failed:'+safeDiagnosticError(error));
          throw error;
        }));
      }
      return;
    }
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

