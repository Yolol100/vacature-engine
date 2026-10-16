// One-time, private and read-only reliability check, triggered solely by a D1 admin marker.
// Runs one registered ATS per Cron while RADAR_ENABLED=0; never changes vacancy/application data.
export const RELIABILITY_REQUEST_KEY = 'reliability_request:2026-10-16';
export const RELIABILITY_RESULT_KEY = 'reliability_result:2026-10-16';
const EXPIRY_MS = Date.parse('2026-10-18T23:59:59Z');
const MAX_SOURCES = 3;
const MAX_JOBS = 160;

export function safeDiagnosticError(error) {
  const raw = String(error?.message || '');
  if (/^Google OAuth HTTP [45]\d\d$/.test(raw) ||
    /^Sheets (read|update|clear) HTTP [45]\d\d$/.test(raw) ||
    /^Public API HTTP [45]\d\d$/.test(raw) ||
    /^(Missing required Worker bindings or secrets|Missing Google Sheets service account secret|Missing required Google bindings|Sheets response incomplete|Spreadsheet header mismatch: stop before dedupe or writes|No active ATS\+employer source pairs|Source exceeds safe job limit|Source payload too large|Unexpected public jobs payload|Unexpected ATS job host: source contract changed|Empty first ATS snapshot|Inactive registered source)$/.test(raw))
    return raw.slice(0, 110);
  return 'Unexpected runtime failure';
}
async function meta(db, key) {
  const entry = await db.prepare('SELECT value FROM radar_metadata WHERE name=?').bind(key).first();
  return entry?.value ?? null;
}
async function setMeta(db, key, value) {
  await db.prepare('INSERT INTO radar_metadata(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value')
    .bind(key, String(value)).run();
}
export async function runReliabilityProbe(env, ops) {
  if (env.RADAR_ENABLED !== '0' || !env.RADAR_DB || (ops.now?.() ?? Date.now()) > EXPIRY_MS)
    return {status:'disabled'};
  const db = env.RADAR_DB;
  const request = await meta(db, RELIABILITY_REQUEST_KEY);
  const match = /^([A-Za-z0-9_-]{12,48}):([012])$/.exec(request || '');
  if (!match) return {status:'disabled'};
  const [, id, stageText] = match;
  const stage = Number(stageText);
  if (ops.PILOT_SOURCES.length !== MAX_SOURCES)
    return {status:'invalid_source_configuration'};
  let receipt;
  if (stage === 0) {
    receipt = {test_id:id,status:'in_progress',started_at:new Date().toISOString(),
      google_auth:'not_tested',sheets_read:'not_tested',sources:{}};
  } else {
    try {receipt = JSON.parse(await meta(db, RELIABILITY_RESULT_KEY) || 'null');} catch {receipt=null;}
    if (receipt?.test_id !== id || typeof receipt.sources !== 'object' ||
        Object.keys(receipt.sources).length !== stage)
      return {status:'invalid_checkpoint'};
  }

  // Claim exactly one stage. A second Cron cannot fetch the same stage concurrently.
  const running = 'running:'+id+':'+stage;
  const claim = await db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')
    .bind(running, RELIABILITY_REQUEST_KEY, request).run();
  if (claim.meta?.changes !== 1) return {status:'already_claimed'};

  const source = ops.PILOT_SOURCES[stage];
  const key = source.source_id+':'+source.account;
  const entry = {status:'failed',checked_at:new Date().toISOString()};
  try {
    if (!env.GOOGLE_SERVICE_ACCOUNT_JSON || !env.VACATURE_REGISTER_ID || !env.RADAR_RESULT_ID)
      throw new Error('Missing required Google bindings');
    const token = await ops.accessToken(env);
    receipt.google_auth = 'ok';
    const [sources,vacancies,applications,events] = await ops.readRanges(env.VACATURE_REGISTER_ID,[
      "'Bronnen'!A1:M","'Vacatures'!A1:A1","'Applications'!A1:A1","'ApplicationEvents'!A1:A1"
    ],token);
    const [keys,urls,statuses,actions] = await ops.readRanges(env.RADAR_RESULT_ID,[
      "'Nieuwe vacatures'!A1:A1","'Nieuwe vacatures'!F1:F1",
      "'Nieuwe vacatures'!N1:N1","'Nieuwe vacatures'!R1:R1"
    ],token);
    ops.assertSheetHeaders(sources,vacancies,applications,events,keys,urls,statuses,actions);
    receipt.sheets_read = 'ok';
    if (!ops.sourceActive(sources, source)) throw new Error('Inactive registered source');
    const jobs = await ops.publicJobs(source);
    if (jobs.length === 0) throw new Error('Empty first ATS snapshot');
    if (jobs.length > MAX_JOBS) throw new Error('Source exceeds safe job limit');
    entry.status='ok';
    entry.observations=jobs.length;
  } catch (error) {
    entry.error = safeDiagnosticError(error);
  }
  receipt.sources[key] = entry;
  receipt.last_stage = stage;
  receipt.checked_at = new Date().toISOString();
  const completed = stage === MAX_SOURCES-1;
  receipt.status = completed
    ? (Object.values(receipt.sources).every(s=>s.status==='ok') &&
       receipt.google_auth==='ok' && receipt.sheets_read==='ok' ? 'ok' : 'partial')
    : 'in_progress';
  if (completed) receipt.finished_at = new Date().toISOString();
  // Commit the result before acknowledging the stage; a storage failure keeps it fail-closed.
  await setMeta(db, RELIABILITY_RESULT_KEY, JSON.stringify(receipt));
  const next = completed ? 'done:'+id : id+':'+(stage+1);
  const ack = await db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')
    .bind(next,RELIABILITY_REQUEST_KEY,running).run();
  if (ack.meta?.changes !== 1) throw new Error('Reliability probe stage acknowledgment failed');
  return {status:receipt.status,stage:stage+1,total:MAX_SOURCES,
    source:key,source_status:entry.status,observations:entry.observations??0};
}
