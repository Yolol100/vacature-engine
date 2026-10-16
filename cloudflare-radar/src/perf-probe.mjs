// Ephemeral read-only production-like CPU probe; no public endpoint.
// A D1 administrator can request three once-only Cron invocations while the radar is off.
export const PERF_REQUEST='perf_request:2026-10-16';
export const PERF_RESULT='perf_result:2026-10-16';
const HARD_END=Date.parse('2026-10-17T23:59:59Z');
async function load(db,key){
  return (await db.prepare('SELECT value FROM radar_metadata WHERE name=?').bind(key).first())?.value??null;
}
async function write(db,key,value){
  await db.prepare('INSERT INTO radar_metadata(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value')
    .bind(key,value).run();
}
export async function runPrivateCpuProbe(env,ops){
  if(env.RADAR_ENABLED!=='0'||!env.RADAR_DB)return {status:'disabled'};
  const db=env.RADAR_DB;
  const request=await load(db,PERF_REQUEST);
  if(!request||request.startsWith('done:')||request.startsWith('failed:')||request.startsWith('running:'))
    return {status:'disabled'};
  let ctrl;
  try{ctrl=JSON.parse(request);}catch{return {status:'invalid_control'};}
  const now=ops.now?.()??Date.now(),expiry=Date.parse(ctrl.expires_at||'');
  if(!/^[A-Za-z0-9_-]{12,48}$/.test(ctrl.id||'')||
     !Number.isInteger(ctrl.stage)||ctrl.stage<0||ctrl.stage>=3||
     !Number.isFinite(expiry)||expiry<=now||expiry>now+10*60*1000||
     expiry>HARD_END||ops.sources.length!==3)return {status:'expired_or_invalid'};
  let receipt;
  if(ctrl.stage===0)receipt={id:ctrl.id,status:'in_progress',started_at:new Date(now).toISOString(),sources:[]};
  else{
    try{receipt=JSON.parse(await load(db,PERF_RESULT)||'null');}catch{receipt=null;}
    if(receipt?.id!==ctrl.id||receipt.status!=='in_progress'||
       !Array.isArray(receipt.sources)||receipt.sources.length!==ctrl.stage)
      return {status:'checkpoint_mismatch'};
  }
  const source=ops.sources[ctrl.stage],instance=source.source_id+':'+source.account;
  const token='running:'+ctrl.id+':'+ctrl.stage;
  const locked=await db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')
    .bind(token,PERF_REQUEST,request).run();
  if(locked.meta?.changes!==1)return {status:'already_claimed'};
  const attempt={source:instance,status:'failed',at:new Date(now).toISOString()};
  try{
    const result=await ops.readOnlyTick(env,instance);
    if(result?.source!==instance||result.status!=='ok'||result.observations<=0)
      throw new Error('Read-only acceptance failed');
    attempt.status='ok';
    attempt.observations=result.observations;
    attempt.already_known=result.already_known;
    attempt.new_candidates=result.new_candidates;
  }catch{
    attempt.error='Read-only check failed';
  }
  receipt.sources.push(attempt);
  receipt.status=attempt.status==='ok'?(ctrl.stage===2?'ok':'in_progress'):'failed';
  receipt.last_checked_at=new Date(ops.now?.()??Date.now()).toISOString();
  if(receipt.status!=='in_progress')receipt.finished_at=receipt.last_checked_at;
  await write(db,PERF_RESULT,JSON.stringify(receipt));
  const next=attempt.status==='ok'
    ? (ctrl.stage===2?'done:'+ctrl.id:JSON.stringify({id:ctrl.id,stage:ctrl.stage+1,expires_at:ctrl.expires_at}))
    : 'failed:'+ctrl.id;
  const result=await db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')
    .bind(next,PERF_REQUEST,token).run();
  if(result.meta?.changes!==1)throw new Error('CPU test control acknowledgment failed');
  return {status:receipt.status,stage:ctrl.stage+1,source:instance,observations:attempt.observations??0};
}
