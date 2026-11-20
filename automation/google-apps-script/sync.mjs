/** Safe, non-scheduling sync of an EXISTING spreadsheet-bound Apps Script. */
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

export const RADAR_SHEET_ID = '1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ';
export const REGISTER_ID = '1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0';
export const hashSource = (value) => createHash('sha256').update(value, 'utf8').digest('hex');
const canonicalFiles = (files) => JSON.stringify(
  [...files].sort((a, b) => a.name.localeCompare(b.name)));


function assertSource(value) {
  if (typeof value !== 'string' ||
      !/function\s+runVacatureRadar\s*\(/.test(value) ||
      !value.includes(REGISTER_ID) || !value.includes(RADAR_SHEET_ID)) {
    throw new Error('Source does not identify the expected Vacature Radar scanner');
  }
}

/** Return an exact, safe-to-update snapshot. Never drop unrelated project files. */
export function inspectFiles(content) {
  if (!Array.isArray(content?.files) || !content.files.length) {
    throw new Error('Apps Script project returned no project files');
  }
  const names = new Set();
  const files = content.files.map((file) => {
    if (!file || typeof file.name !== 'string' || !file.name ||
        !['SERVER_JS', 'HTML', 'JSON'].includes(file.type) ||
        typeof file.source !== 'string' || names.has(file.name)) {
      throw new Error('Apps Script project has missing, duplicate or unsupported files');
    }
    names.add(file.name);
    // getContent includes read-only metadata. updateContent only needs these fields.
    return { name: file.name, type: file.type, source: file.source };
  });
  const manifests = files.filter((file) => file.name === 'appsscript' && file.type === 'JSON');
  if (manifests.length !== 1) throw new Error('Missing project manifest; refusing to overwrite');
  try { JSON.parse(manifests[0].source); }
  catch { throw new Error('Invalid project manifest; refusing to overwrite'); }
  const candidates = files.filter((file) => file.type === 'SERVER_JS' &&
    /function\s+runVacatureRadar\s*\(/.test(file.source));
  if (candidates.length !== 1) throw new Error('Cannot uniquely identify live radar code file');
  assertSource(candidates[0].source);
  return { files, radarFile: candidates[0], sha256: hashSource(candidates[0].source) };
}

export function updatedFiles(snapshot, desiredSource) {
  assertSource(desiredSource);
  return snapshot.files.map((file) => file.name === snapshot.radarFile.name ?
    { ...file, source: desiredSource } : { ...file });
}

async function jsonResponse(response, label) {
  if (!response.ok) throw new Error(`${label} failed: HTTP ${response.status}`);
  const data = await response.json();
  if (!data || typeof data !== 'object') throw new Error(`${label} returned invalid JSON`);
  return data;
}

export async function synchronize({ mode, env = process.env, fetchImpl = fetch,
  readSource = () => readFile(new URL('./Code.gs', import.meta.url), 'utf8'),
  log = console.log } = {}) {
  if (!['inspect', 'healthcheck', 'deploy'].includes(mode)) throw new Error('Use inspect, healthcheck or deploy');
  const required = ['RADAR_SCRIPT_ID', 'RADAR_GOOGLE_CLIENT_ID',
    'RADAR_GOOGLE_CLIENT_SECRET', 'RADAR_GOOGLE_REFRESH_TOKEN'];
  for (const key of required) {
    if (!env[key]) throw new Error(`Missing required GitHub secret: ${key}`);
  }
  const scriptId = env.RADAR_SCRIPT_ID;
  if (!/^[\w-]{20,}$/.test(scriptId)) throw new Error('Invalid script project ID');
  const desiredSource = await readSource();
  assertSource(desiredSource);
  const desiredHash = hashSource(desiredSource);
  const params = new URLSearchParams({
    client_id: env.RADAR_GOOGLE_CLIENT_ID,
    client_secret: env.RADAR_GOOGLE_CLIENT_SECRET,
    refresh_token: env.RADAR_GOOGLE_REFRESH_TOKEN,
    grant_type: 'refresh_token'
  });
  const auth = await jsonResponse(await fetchImpl('https://oauth2.googleapis.com/token', {
    method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: params.toString()
  }), 'Google OAuth');
  if (typeof auth.access_token !== 'string' || !auth.access_token) {
    throw new Error('Google OAuth did not return an access token');
  }
  const base = `https://script.googleapis.com/v1/projects/${encodeURIComponent(scriptId)}`;
  async function api(path, method = 'GET', body) {
    const response = await fetchImpl(base + path, {
      method,
      headers: { Authorization: `Bearer ${auth.access_token}`,
        ...(body ? {'Content-Type': 'application/json'} : {}) },
      ...(body ? {body: JSON.stringify(body)} : {})
    });
    return jsonResponse(response, `Apps Script ${method} ${path}`);
  }
  const project = await api('');
  if (project.scriptId !== scriptId || project.parentId !== RADAR_SHEET_ID) {
    throw new Error('Project is not the expected spreadsheet-bound Vacature Radar; no write');
  }
  let snapshot = inspectFiles(await api('/content'));
  log(`Live code file: ${snapshot.radarFile.name}`);
  log(`Live SHA256: ${snapshot.sha256}`);
  log(`GitHub SHA256: ${desiredHash}`);
  if (mode === 'inspect' || mode === 'healthcheck') {
    const matches = snapshot.sha256 === desiredHash;
    log(matches ? 'PASS: live code matches GitHub' :
      'DIFFERENT: inspect and approve the live baseline before deployment');
    if (mode === 'healthcheck' && !matches) {
      throw new Error('CODE_DRIFT: live scanner differs from GitHub; inspect before deployment');
    }
    return { state: mode === 'healthcheck' ? 'HEALTHY' : 'INSPECTED',
      liveHash: snapshot.sha256, desiredHash };
  }
  if (snapshot.sha256 === desiredHash) {
    log('NO_CHANGE: same scanner code already installed; no write');
    return { state: 'NO_CHANGE', liveHash: snapshot.sha256, desiredHash };
  }
  if (env.RADAR_EXPECTED_GITHUB_SHA256 !== desiredHash) {
    throw new Error('Expected GitHub SHA256 missing or mismatched; refusing deployment');
  }
  const approved = env.RADAR_APPROVED_LIVE_SHA256S ?
    env.RADAR_APPROVED_LIVE_SHA256S.split(',') : [env.RADAR_EXPECTED_LIVE_SHA256];
  if (approved.length === 0 || approved.length > 100 ||
      approved.some((digest) => !/^[a-f0-9]{64}$/.test(digest || '')) ||
      !approved.includes(snapshot.sha256)) {
    throw new Error('Expected live SHA256 missing or mismatched; refusing deployment');
  }
  // Re-read immediately before PUT to reduce overwriting a simultaneous editor change.
  const fresh = inspectFiles(await api('/content'));
  if (fresh.sha256 !== snapshot.sha256 ||
      canonicalFiles(fresh.files) !== canonicalFiles(snapshot.files)) {
    throw new Error('Live project changed during preflight; refusing deployment');
  }
  await api('/content', 'PUT', {files: updatedFiles(fresh, desiredSource)});
  const verified = inspectFiles(await api('/content'));
  if (verified.sha256 !== desiredHash ||
      canonicalFiles(verified.files) !== canonicalFiles(updatedFiles(fresh, desiredSource))) {
    throw new Error('WRITE_NOT_VERIFIED: live readback differs; inspect before any retry');
  }
  log('PASS: updated existing scanner file; preserved other files and manifest');
  log('Trigger count and execution success are NOT verified by this code sync');
  return { state: 'DEPLOYED', liveHash: verified.sha256, desiredHash };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  synchronize({mode: process.argv[2]}).catch((error) => {
    console.error(`BLOCKED: ${error.message}`);
    process.exitCode = 1;
  });
}
