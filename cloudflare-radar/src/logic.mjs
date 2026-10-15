// Transport-only helpers; policy always belongs to live Vacature Register.
export const PILOT_SOURCES = Object.freeze([
  {source_id:'greenhouse',account:'automatticcareers',employer_source_id:'company-automattic',employer:'Automattic'},
  {source_id:'lever',account:'kinsta',employer_source_id:'company-kinsta',employer:'Kinsta'},
  {source_id:'ashby',account:'zapier',employer_source_id:'company-zapier',employer:'Zapier'}
]);
const TRACKING = new Set(['ref','source','campaign','gh_src','mc_cid','mc_eid','li_fat_id','referral']);
const SUBMITTED = new Set(['submitted','applied','screen','interview','assessment','final','offer','rejected','withdrawn','closed']);
const KNOWN = new Set(['seen','shown','submitted','applied','screen','interview','assessment','final','offer','rejected','withdrawn','closed','excluded_user_preference','excluded']);
export function canonicalUrl(raw) {
  if (typeof raw !== 'string') return '';
  try {
    const url = new URL(raw);
    if (url.protocol !== 'https:') return '';
    url.hash = '';
    for (const key of [...url.searchParams.keys()]) {
      if (key.toLowerCase().startsWith('utm_') || TRACKING.has(key.toLowerCase())) url.searchParams.delete(key);
    }
    return url.toString().replace(/\/$/, '');
  } catch { return ''; }
}
export function sourceActive(rows, source) {
  const states = new Map(rows.slice(1).filter(r => r[0]).map(r => [r[0],r[12]]));
  return states.get(source.source_id) === 'active' && states.get(source.employer_source_id) === 'active';
}
export function normalizeJobs(source, payload) {
  const jobs = Array.isArray(payload) ? payload : payload?.jobs;
  if (!Array.isArray(jobs)) throw new Error('Unexpected public jobs payload');
  return jobs.filter(job => !(source.source_id === 'ashby' && job.isListed === false)).map(job => {
    const id = String(job.id ?? (source.source_id === 'ashby' ? canonicalUrl(job.jobUrl) : '')).trim();
    const title = String(source.source_id === 'lever' ? (job.text ?? '') : (job.title ?? '')).trim();
    const url = canonicalUrl(source.source_id === 'lever' ? (job.hostedUrl ?? '') : source.source_id === 'ashby' ? (job.jobUrl ?? '') : (job.absolute_url ?? ''));
    const location = String(source.source_id === 'lever' ? (job.categories?.location ?? '') : (typeof job.location === 'string' ? job.location : job.location?.name ?? '')).trim();
    const remote = String(job.workplaceType ?? '').trim();
    return {identity:source.source_id+':'+source.account+':'+id,source_id:source.source_id,source_job_id:id,employer:source.employer,title,url,source_url:url,location,remote,language:'',confirmed_published_at:''};
  }).filter(x => x.source_job_id && x.title && x.url);
}
export function registerKnown(vacatures, applications) {
  const knownUrls = new Set(), submittedIds = new Set();
  for (const a of applications.slice(1)) {
    if (!a?.[0] || /^(test:|history:)/.test(a[0])) continue;
    if (SUBMITTED.has(String(a[2] || '').toLowerCase())) {
      submittedIds.add(a[0]);
      const url = canonicalUrl(a[4]);
      if (url) knownUrls.add(url);
    }
  }
  for (const row of vacatures.slice(1)) {
    const id = String(row[0] || '');
    if (!id || /^(test:|history:)/.test(id)) continue;
    const status = String(row[1] || '').toLowerCase();
    if (!KNOWN.has(status) && !submittedIds.has(id)) continue;
    for (const value of [row[6],row[7]]) {
      const url = canonicalUrl(value);
      if (url) knownUrls.add(url);
    }
  }
  return knownUrls;
}
export function shouldSuppress(job, registeredUrls, radarUrls, existingIdentityKeys) {
  return registeredUrls.has(job.url) || radarUrls.has(job.url) || existingIdentityKeys.has(job.identity);
}
export function toRadarRow(job, now, runId) {
  return [job.identity,job.source_id,job.source_job_id,job.employer,job.title,job.url,job.source_url,
    job.remote,job.location,job.language,job.confirmed_published_at,now,now,'onbekend','ontdekt','onbekend',
    'niet_beoordeeld','officiele_verificatie_nodig','Technische eerste detectie; publicatietijd niet bewezen; geen bevestigde match.','',runId];
}
export function adapterUrl(source) {
  if (source.source_id === 'greenhouse') return 'https://boards-api.greenhouse.io/v1/boards/'+encodeURIComponent(source.account)+'/jobs';
  if (source.source_id === 'lever') return 'https://api.lever.co/v0/postings/'+encodeURIComponent(source.account)+'?mode=json';
  if (source.source_id === 'ashby') return 'https://api.ashbyhq.com/posting-api/job-board/'+encodeURIComponent(source.account);
  throw new Error('Unsupported adapter');
}
export function isValidJob(job) {
  if (!job.identity || !job.url || !job.title) return false;
  const host = new URL(job.url).hostname;
  if (job.source_id === 'greenhouse') return host === 'boards.greenhouse.io' || host === 'job-boards.greenhouse.io';
  if (job.source_id === 'lever') return host === 'jobs.lever.co';
  if (job.source_id === 'ashby') return host === 'jobs.ashbyhq.com';
  return false;
}
