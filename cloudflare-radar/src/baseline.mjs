// Private, time-limited live baseline executed by the REAL production tick.
// Arm with a single D1-only control record; no public endpoint, no default activation.
// Each scheduled invocation may bootstrap exactly ONE whitelisted registered ATS source.
// Fails closed on crash, timeout, error, unexpected state or concurrent invocation.
import {safeDiagnosticError} from './health.mjs';

export const CONTROL_KEY='baseline_control:2026-10-16';
export const RECEIPT_KEY='baseline_receipt:2026-10-16';
const ABSOLUTE_END=Date.parse('2026-10-17T23:59:59Z');
const MAX_WINDOW_MS=12*60*1000;

async function getMeta(db,key){
  return (await db.prepare('SELECT value FROM radar_metadata WHERE name=?').bind(key).first())?.value??null;
}
async function setMeta(db,key,value){
  await db.prepare('INSERT INTO radar_metadata(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value')
    .bind(key,String(value)).run();
}

export async function runControlledBaseline(env,ops){
  if(env.RADAR_ENABLED!=='0'||!env.RADAR_DB)return {status:'disabled'};
  const db=env.RADAR_DB,raw=await getMeta(db,CONTROL_KEY);
  if(!raw||raw.startsWith('running:')||raw.startsWith('done:')||raw.startsWith('failed:'))return {status:'disabled'};
  let state;
  try{state=JSON.parse(raw);}catch{return {status:'invalid_control'};}
  const now=(ops.now?.()??Date.now()),expiry=Date.parse(state.expires_at||'');
  if(!/^[A-Za-z0-9_-]{12,48}$/.test(state.id||'')||
     !Number.isInteger(state.stage)||state.stage<0||state.stage>=3||
     !Number.isFinite(expiry)||expiry<=now||expiry>now+MAX_WINDOW_MS||
     expiry>ABSOLUTE_END||ops.PILOT_SOURCES.length!==3)
    return {status:'invalid_or_expired_control'};
  let receipt;
  if(state.stage===0){
    receipt={id:state.id,status:'in_progress',started_at:new Date(now).toISOString(),sources:[]};
  }else{
    try{receipt=JSON.parse(await getMeta(db,RECEIPT_KEY)||'null');}catch{receipt=null;}
    if(receipt?.id!==state.id||receipt.status!=='in_progress'||
       !Array.isArray(receipt.sources)||receipt.sources.length!==state.stage)
      return {status:'checkpoint_mismatch'};
  }
  const source=ops.PILOT_SOURCES[state.stage];
  const instance=source.source_id+':'+source.account;
  const running='running:'+state.id+':'+state.stage;
  const claim=await db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')
    .bind(running,CONTROL_KEY,raw).run();
  if(claim.meta?.changes!==1)return {status:'already_claimed'};

  let success=false;
  const attempt={source:instance,status:'failed',at:new Date(now).toISOString()};
  try{
    if(await getMeta(db,'seeded:'+instance))throw new Error('Baseline previously seeded');
    const prior=await db.prepare('SELECT COUNT(*) AS n FROM radar_observations WHERE source_instance=?')
      .bind(instance).first();
    if(Number(prior?.n||0)!==0)throw new Error('Baseline observation collision');
    const result=await ops.tick({...env,RADAR_ENABLED:'1',BASELINE_SOURCE_INSTANCE:instance});
    const after=await getMeta(db,'seeded:'+instance);
    const counts=await db.prepare('SELECT COUNT(*) AS n FROM radar_observations WHERE source_instance=? AND status=?')
      .bind(instance,'baseline').first();
    const count=Number(counts?.n||0);
    if(result?.status!=='ok'||result.sources!==1||result.new_records!==0||
       result.applied_reconciled!==0||!after||count<=0||
       count!==result.observations)
      throw new Error('Baseline tick acceptance check failed');
    attempt.status='ok';
    attempt.observations=count;
    success=true;
  }catch(error){
    attempt.error=safeDiagnosticError(error);
  }
  receipt.sources.push(attempt);
  receipt.last_checked_at=new Date(ops.now?.()??Date.now()).toISOString();
  receipt.status=success?(state.stage===2?'ok':'in_progress'):'failed';
  if(receipt.status!=='in_progress')receipt.finished_at=receipt.last_checked_at;
  // Durable evidence before finalizing the control. Crash at any point fails closed.
  await setMeta(db,RECEIPT_KEY,JSON.stringify(receipt));
  const next=success?(state.stage===2?'done:'+state.id:JSON.stringify({
    id:state.id,stage:state.stage+1,expires_at:state.expires_at
  })):'failed:'+state.id;
  const ack=await db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')
    .bind(next,CONTROL_KEY,running).run();
  if(ack.meta?.changes!==1)throw new Error('Baseline control acknowledgement failed');
  return {status:receipt.status,stage:state.stage+1,total:3,
    source:instance,source_status:attempt.status,observations:attempt.observations??0};
}
