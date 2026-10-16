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
    // TEMPORARY: a private D1 permit authorizes at most ONE read-only cycle.
    // Both real production switches stay off. Never expose a public trigger.
    if(env.RADAR_CPU_CANARY==='1'&&env.RADAR_ENABLED==='0'&&
       env.RADAR_PIPELINE_MODE==='off'&&env.RADAR_DB){
      const row=await env.RADAR_DB.prepare('SELECT value FROM radar_metadata WHERE name=?')
        .bind('micro:v2:cpu_canary').first();
      let permit;
      try{permit=JSON.parse(row?.value||'null');}catch{permit=null;}
      const now=Date.now();
      if(permit?.kind==='slim-bundle-free-cpu-20261017'&&
         Number.isSafeInteger(permit.started)&&Number.isSafeInteger(permit.until)&&
         permit.started<=now&&now<permit.until&&
         permit.until-permit.started<=7*60000){
        const isolated={...env,RADAR_ENABLED:'1',RADAR_PIPELINE_MODE:'staged_review'};
        ctx.waitUntil(runStagedReview(isolated,{
          accessToken,readRanges,publicJobs,existingKeys,
          pagedVacancy:true,splitBootstrap:true,singleCycle:true
        }).then(outcome=>{
          console.log(JSON.stringify({private_cpu_sample:true,status:outcome.status,
            phase:outcome.phase||null,phase_index:outcome.phase_index||null}));
        }).catch(error=>{
          console.error('private_cpu_sample_failed:'+safeDiagnosticError(error));
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

