// Bounded and credential-free health metadata for active production polls.
// This cannot detect a permanently stopped scheduler on its own; it flags gaps when Cron resumes.
export function safeDiagnosticError(error){
  const raw=String(error?.message||'');
  if(/^Google OAuth HTTP [45]\d\d$/.test(raw) ||
     /^Sheets (read|update|clear) HTTP [45]\d\d$/.test(raw) ||
     /^Public API HTTP [45]\d\d$/.test(raw) ||
     /^(Missing required Worker bindings or secrets|Missing Google Sheets service account secret|Spreadsheet header mismatch: stop before dedupe or writes|No active ATS\+employer source pairs|Source exceeds safe job limit|Source payload too large|Unexpected public jobs payload|Unexpected ATS job host: source contract changed)$/.test(raw))
    return raw.slice(0,110);
  return 'Unexpected runtime failure';
}
const GAP_MS=6*60*1000;
async function getMeta(db,key){
  const row=await db.prepare('SELECT value FROM radar_metadata WHERE name=?').bind(key).first();
  return row?.value??null;
}
async function putMeta(db,key,value){
  await db.prepare('INSERT INTO radar_metadata(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value')
    .bind(key,String(value)).run();
}
export async function monitoredTick(env,run,clock=()=>Date.now()){
  if(env.RADAR_ENABLED!=='1') return {status:'disabled'};
  if(!env.RADAR_DB) return run(env);
  const db=env.RADAR_DB, now=clock(), started=new Date(now).toISOString();
  const previous=await getMeta(db,'health:last_started_utc');
  const last=Date.parse(previous||'');
  if(Number.isFinite(last)&&now-last>GAP_MS){
    await putMeta(db,'health:last_gap',JSON.stringify({detected_at:started,gap_minutes:Math.floor((now-last)/60000)}));
    console.warn('vacature_radar_cron_gap_detected');
  }
  await putMeta(db,'health:last_started_utc',started);
  try{
    const result=await run(env);
    const status=String(result?.status||'unknown');
    await putMeta(db,'health:last_result',JSON.stringify({
      at:new Date(clock()).toISOString(),status,
      sources:Number(result?.sources)||0,
      errors:Number(result?.errors)||0,
      delivered:Number(result?.new_records)||0
    }));
    if(status==='ok') await putMeta(db,'health:last_ok_utc',new Date(clock()).toISOString());
    if(status==='partial'){
      await putMeta(db,'health:last_failure',JSON.stringify({at:new Date(clock()).toISOString(),reason:'Partial ATS poll'}));
      console.error(new Error('Vacature Radar ATS poll partial'));
    }
    return result;
  }catch(error){
    const reason=safeDiagnosticError(error);
    try{
      await putMeta(db,'health:last_failure',JSON.stringify({at:new Date(clock()).toISOString(),reason}));
      await putMeta(db,'health:last_result',JSON.stringify({at:new Date(clock()).toISOString(),status:'failed',errors:1}));
    }catch{
      // Preserve the original exception even when the D1 health sink is unavailable.
    }
    throw error;
  }
}
