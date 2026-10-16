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
    // TEMPORARY READ-ONLY CPU PROBE; independent private D1 lease required.
    // Production stays disabled, and the real scheduled path remains unchanged.
    if(env.RADAR_CPU_CANARY==='1'&&env.RADAR_ENABLED==='0'&&
       env.RADAR_PIPELINE_MODE==='off'&&env.RADAR_DB){
      const item=await env.RADAR_DB.prepare('SELECT value FROM radar_metadata WHERE name=?')
        .bind('micro:v2:cpu_canary').first();
      let lease;
      try{lease=JSON.parse(item?.value||'null');}catch{lease=null;}
      const now=Date.now();
      if(lease?.kind==='slim-worker-cpu-20261017'&&
         Number.isSafeInteger(lease.started)&&Number.isSafeInteger(lease.until)&&
         lease.started<=now&&now<lease.until&&
         lease.until-lease.started<=8*60000){
        const isolated={...env,RADAR_ENABLED:'1',RADAR_PIPELINE_MODE:'staged_review'};
        const ops={accessToken,readRanges,publicJobs,existingKeys,
          pagedVacancy:true,splitBootstrap:true,singleCycle:true};
        ctx.waitUntil(runStagedReview(isolated,ops).then(outcome=>{
          console.log(JSON.stringify({private_cpu:true,status:outcome.status,
            phase:outcome.phase||null,phase_index:outcome.phase_index||null}));
        }).catch(error=>{
          console.error('private_cpu_failure:'+safeDiagnosticError(error));
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

