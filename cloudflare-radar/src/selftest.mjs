// One-shot, private Cron diagnostic. Only a privileged D1 write can request it.
// It never changes vacancy records, application statuses, or the radar enabled flag.
export const SMOKE_REQUEST_KEY = 'smoke_request:2026-10-16';
export const SMOKE_RESULT_KEY = 'smoke_result:2026-10-16';
const EXPIRY = Date.parse('2026-10-17T23:59:59Z');
const TEST_CELL = "'Runs'!L1000";

function safeError(error) {
  const message = String(error?.message || '');
  return /^(Missing required|Missing Google|Google OAuth HTTP \d{3}|Sheets (read|update|clear) HTTP \d{3}|Incomplete Sheets|Spreadsheet header mismatch|No active|Public API HTTP \d{3}|Source exceeds|Source payload|Unexpected public jobs|Unexpected ATS job|Google test cell|Google test cleanup)/.test(message)
    ? message.slice(0, 120) : 'Unexpected test failure';
}
async function putMeta(db, name, value) {
  await db.prepare('INSERT INTO radar_metadata(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value')
    .bind(name, value).run();
}
export async function runOneTimeSmokeTest(env, ops) {
  // No HTTP endpoint; inactive by default, expires after the initial setup.
  if (env.RADAR_ENABLED !== '0' || !env.RADAR_DB || (ops.now?.() ?? Date.now()) > EXPIRY)
    return {status:'disabled'};
  const db = env.RADAR_DB;
  const request = (await db.prepare('SELECT value FROM radar_metadata WHERE name=?')
    .bind(SMOKE_REQUEST_KEY).first())?.value;
  if (!/^[A-Za-z0-9_-]{12,64}$/.test(request || ''))
    return {status:'disabled'};
  const claim = await db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')
    .bind('running:'+request, SMOKE_REQUEST_KEY, request).run();
  if (claim.meta?.changes !== 1)
    return {status:'already_claimed'};

  const outcome = {
    test_id:request,started_at:new Date().toISOString(),
    status:'failed',google_auth:'not_tested',sheets_read:'not_tested',
    sheets_write:'not_tested',cleanup:'not_needed',ats:'not_tested'
  };
  try {
    if (!env.GOOGLE_SERVICE_ACCOUNT_JSON || !env.VACATURE_REGISTER_ID || !env.RADAR_RESULT_ID)
      throw new Error('Missing required Google test bindings');
    const token = await ops.accessToken(env);
    outcome.google_auth = 'ok';
    const [sources, vacancies, applications, events] = await ops.readRanges(
      env.VACATURE_REGISTER_ID,
      ["'Bronnen'!A1:M","'Vacatures'!A1:H1","'Applications'!A1:E1","'ApplicationEvents'!A1:F1"],
      token);
    const [keys, urls, statuses, actions] = await ops.readRanges(
      env.RADAR_RESULT_ID,
      ["'Nieuwe vacatures'!A1:A1","'Nieuwe vacatures'!F1:F1",
        "'Nieuwe vacatures'!N1:N1","'Nieuwe vacatures'!R1:R1"],
      token);
    ops.assertSheetHeaders(sources, vacancies, applications, events, keys, urls, statuses, actions);
    outcome.sheets_read = 'ok';

    // The last cell of Runs is outside the existing A:L reporting rows.
    // Refuse to overwrite a nonempty cell; always clean up even if a write times out.
    const before = await ops.readRanges(env.RADAR_RESULT_ID, [TEST_CELL], token);
    if (before[0]?.length) throw new Error('Google test cell is not empty');
    const marker = '__vacature_radar_selftest__'+request;
    let attempted = false;
    try {
      attempted = true;
      await ops.updateCells(env.RADAR_RESULT_ID, [{range:TEST_CELL,value:marker}], token);
      const readback = await ops.readRanges(env.RADAR_RESULT_ID, [TEST_CELL], token);
      if (readback[0]?.[0]?.[0] !== marker)
        throw new Error('Google test cell readback mismatch');
      outcome.sheets_write = 'ok';
    } finally {
      if (attempted) {
        try {
          await ops.clearCell(env.RADAR_RESULT_ID, TEST_CELL, token);
          const after = await ops.readRanges(env.RADAR_RESULT_ID, [TEST_CELL], token);
          outcome.cleanup = after[0]?.length ? 'failed' : 'ok';
        } catch {
          outcome.cleanup = 'failed';
        }
      }
    }
    if (outcome.cleanup !== 'ok') throw new Error('Google test cleanup failed');
    const active = ops.PILOT_SOURCES.filter(source => ops.sourceActive(sources, source));
    if (!active.length) throw new Error('No active ATS and employer sources');
    const selected = active.find(source => source.source_id === 'lever') || active[0];
    outcome.ats_source = selected.source_id + ':' + selected.account;
    try {
      const jobs = await ops.publicJobs(selected);
      outcome.ats = 'ok';
      outcome.ats_job_count = jobs.length;
      outcome.status = 'ok';
    } catch (error) {
      outcome.ats = 'failed';
      outcome.ats_error = safeError(error);
      outcome.status = 'partial';
    }
  } catch (error) {
    outcome.error = safeError(error);
  } finally {
    outcome.finished_at = new Date().toISOString();
    await putMeta(db, SMOKE_RESULT_KEY, JSON.stringify(outcome));
    await db.prepare('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')
      .bind('done:'+request, SMOKE_REQUEST_KEY, 'running:'+request).run();
  }
  return {status:outcome.status,google_auth:outcome.google_auth,
    sheets_read:outcome.sheets_read,sheets_write:outcome.sheets_write,
    cleanup:outcome.cleanup,ats:outcome.ats};
}
