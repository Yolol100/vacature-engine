/**
 * Vacature Radar fast lane for a spreadsheet-bound Google Apps Script.
 *
 * No Cloudflare, paid API, applicant submission or canonical Register writes.
 * All discoveries are UNVERIFIED leads in the EXISTING Radar spreadsheet.
 * A user must intentionally run enableVacatureRadar() in the Apps Script editor.
 */
var VACATURE_RADAR = {
  registerId: '1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0',
  radarId: '1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ',
  specsUrl: 'https://raw.githubusercontent.com/Yolol100/vacature-engine/main/ingestion/source-specs.deploy.json',
  allowedSchedule: 'apps_script_15m_fastlane_and_on_demand_deep',
  maxRequests: 35,
  maxJobsPerSource: 250,
  maxNewRows: 150,
  maxRuntimeMs: 240000
};

var RADAR_LEAD_COLUMNS = [
  'candidate_key', 'first_seen_utc', 'last_seen_utc', 'source_id',
  'source_job_id', 'employer', 'title', 'official_or_board_url',
  'published_hint', 'location', 'review_status', 'source_type',
  'review_note'
];

function radarTab_(file, title) {
  var tab = file.getSheetByName(title);
  if (!tab) throw new Error('Required sheet is missing: ' + title);
  return tab;
}

function radarRecordMap_(sheet) {
  var values = sheet.getDataRange().getValues();
  if (!values.length) throw new Error('Missing headers in: ' + sheet.getName());
  var header = values[0].map(function (x) { return String(x || '').trim(); });
  var names = {};
  header.forEach(function (name, i) {
    if (name) {
      if (Object.prototype.hasOwnProperty.call(names, name)) {
        throw new Error('Duplicate column: ' + name);
      }
      names[name] = i;
    }
  });
  return { header: header, names: names, values: values.slice(1) };
}

function radarSafeCell_(value) {
  var text = String(value == null ? '' : value).slice(0, 1200);
  return /^[=+\-@\t\r]/.test(text) ? "'" + text : text;
}

function radarNormalizeUrl_(value) {
  if (typeof value !== 'string' || !/^https:\/\/[a-z0-9][a-z0-9.-]*\//i.test(value)) return '';
  var noFragment = value.split('#', 1)[0];
  var pieces = noFragment.split('?');
  var host = pieces[0].match(/^https:\/\/([^/:]+)/i);
  if (!host || /(?:^|\.)(?:localhost|local|internal)$/.test(host[1].toLowerCase())) return '';
  if (/^\d+\.\d+\.\d+\.\d+$/.test(host[1])) return '';
  if (pieces.length === 1) return pieces[0].replace(/\/+$/, '');
  var filtered = pieces.slice(1).join('?').split('&').filter(function (parameter) {
    var key = parameter.split('=')[0].toLowerCase();
    return !!key && !/^utm_|^(?:fbclid|gclid|msclkid)$/.test(key);
  });
  return pieces[0].replace(/\/+$/, '') + (filtered.length ? '?' + filtered.join('&') : '');
}

function radarRelevant_(title, description, family) {
  var t = String(title || '').toLowerCase();
  var d = String(description || '').slice(0, 16000).toLowerCase()
    .replace(/<[^>]+>/g, ' ').replace(/&nbsp;|&#160;/g, ' ');
  // A standalone engineering, operations, sales, AI or product role is not
  // WordPress work merely because the company uses a WordPress website.
  if (/\b(ai automation|sales engineer|systems engineer|onboarding engineer|product designer|mobile developer|data engineer)\b/.test(t) &&
      !/\b(wordpress|woocommerce|elementor|gutenberg|acf|wpml)\b/.test(t)) return false;
  if (/\b(wordpress|woocommerce|elementor|gutenberg|wpml|acf)\b/.test(t)) return true;
  var relevantTitle = /\b(web\s?designer|web\s?developer|frontend|front.end|php developer|php engineer|website|web ux|web ui|theme developer|plugin developer)\b/.test(t);
  var relevantDuty = /(?:build|develop|maintain|customiz|migrat|implement|design|support|create|work with|bouwen|ontwikkel|onderhoud|beheer|ontwerp|migrer|plugins|themes)[\s\S]{0,90}\b(wordpress|woocommerce|elementor|gutenberg|acf|wpml)\b|\b(wordpress|woocommerce|elementor|gutenberg|acf|wpml)\b[\s\S]{0,90}(?:build|develop|maintain|customiz|migrat|implement|design|support|create|bouwen|ontwikkel|onderhoud|beheer|ontwerp|plugins|themes)/.test(d);
  if (relevantTitle && relevantDuty) return true;
  return family.indexOf('web_design_development') !== -1 &&
    /\bweb\s?designer\b|\bfront.?end\b|\bwebsite\b|\bweb developer\b|\bweb ux\b/.test(t);
}

function radarPublicationMs_(hint) {
  var text = String(hint == null ? '' : hint).trim();
  if (!text) return NaN;
  // Himalayas pubDate is Unix seconds. Also accept milliseconds only
  // when the exact integer shape is present; don't guess other numbers.
  if (/^\d{10}$/.test(text)) return Number(text) * 1000;
  if (/^\d{13}$/.test(text)) return Number(text);
  return Date.parse(text);
}

function radarReview_(job, config, nowMs) {
  var maxAge = Number(config.max_posting_age_days);
  if (!Number.isFinite(maxAge) || maxAge < 1 || maxAge > 90) maxAge = 7;
  var published = radarPublicationMs_(job.publishedHint);
  if (Number.isFinite(published) && published > nowMs + 86400000) {
    return {status: 'date_conflict_review', alert: false, reason: 'Future publication hint'};
  }
  if (Number.isFinite(published) && nowMs - published > maxAge * 86400000) {
    return {status: 'historical_review', alert: false, reason: 'Posting hint older than ' + maxAge + ' days'};
  }
  if (!Number.isFinite(published)) {
    return {status: 'date_unknown_review', alert: false, reason: 'Original posting date unverified'};
  }
  var geo = (String(job.location || '') + ' ' + String(job.description || '').slice(0, 10000)).toLowerCase()
    .replace(/<[^>]+>/g, ' ');
  var location = String(job.location || '').toLowerCase();
  if (/\b(?:us|usa|united states|canada)\s*(?:only|based|residents)|(?:only|based|residents)\s*(?:in|from)\s*(?:us|usa|united states|canada)\b/.test(geo) &&
      !/\b(?:netherlands|europe|emea|worldwide|global)\b/.test(location)) {
    return {status: 'geography_restricted_review', alert: false, reason: 'North America restriction; check NL eligibility'};
  }
  if (/\b(hybrid|on.site|in.office|office.based)\b/.test(location)) {
    return {status: 'not_fully_remote_review', alert: false, reason: 'Location indicates hybrid/on-site'};
  }
  var remote = /\b(remote|fully remote|work from anywhere|distributed|thuiswerken|op afstand)\b/.test(geo);
  // Employer location and candidate geography take priority. A job
  // description may mention Europe as a *customer market* while the
  // role is restricted to Spain or another country.
  var eligibleGeo = /\b(netherlands|nederland|europe|eu remote|emea|worldwide|global|anywhere)\b/.test(location);
  if (!eligibleGeo && /^\s*remote\s*$/.test(location)) {
    var directEligibility = /\b(?:work|working)\s+from\s+anywhere\s+(?:in|within|across)\s+(?:the\s+)?(?:netherlands|nederland|europe|emea)\b|\b(?:you\s+can\s+be\s+)?based\s+anywhere\s+(?:in|within|across)\s+(?:the\s+)?(?:netherlands|nederland|europe|emea)\b|\b(?:work|working)\s+(?:from\s+)?(?:the\s+)?(?:netherlands|nederland|europe|emea)\b/.test(geo);
    eligibleGeo = directEligibility ||
      /\b(?:candidates?|applicants?|residents?|working from|hire|hiring)\b[\s\S]{0,60}\b(?:netherlands|nederland|europe|emea|worldwide|anywhere)\b/.test(geo);
  }
  if (!remote || !eligibleGeo) {
    return {status: 'remote_nl_unknown_review', alert: false, reason: 'Full remote and NL eligibility still unverified'};
  }
  // This is only a promising observation, never proof of employer eligibility.
  return {status: 'needs_official_review', alert: true, reason: 'Recent remote/NL signal; official verification still required'};
}

function radarKnownUrls_(register, radar) {
  var found = {};
  var targets = [
    {sheet: radarTab_(register, 'Vacatures'), columns: ['canonical_url', 'official_url']},
    {sheet: radarTab_(register, 'Applications'), columns: ['application_url']},
    {sheet: radarTab_(register, 'JobSnapshots'), columns: ['canonical_url']},
    {sheet: radarTab_(radar, 'Nieuwe vacatures'), columns: ['officiele_url']}
  ];
  targets.forEach(function (target) {
    var mapped = radarRecordMap_(target.sheet);
    target.columns.forEach(function (column) {
      var index = mapped.names[column];
      if (index == null) return;
      mapped.values.forEach(function (row) {
        var url = radarNormalizeUrl_(String(row[index] || ''));
        if (url) found[url] = true;
      });
    });
  });
  return found;
}

function radarSources_(register) {
  var mapped = radarRecordMap_(radarTab_(register, 'Bronnen'));
  var ids = {};
  mapped.values.forEach(function (row) {
    if (String(row[mapped.names.status] || '').toLowerCase() === 'active') {
      ids[String(row[mapped.names.source_id] || '')] = true;
    }
  });
  if (!Object.keys(ids).length) throw new Error('No approved active source IDs');
  return ids;
}

function radarConfig_(register) {
  var mapped = radarRecordMap_(radarTab_(register, 'Config'));
  var config = {}, position = {};
  mapped.values.forEach(function (row, i) {
    var key = String(row[mapped.names.key] || '');
    if (key) {
      config[key] = String(row[mapped.names.value] == null ? '' : row[mapped.names.value]);
      position[key] = i + 2;
    }
  });
  return { config: config, rows: position };
}

function radarHttp_(url) {
  var response = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    followRedirects: false,
    headers: {Accept: 'application/json, application/rss+xml, application/xml, text/xml'}
  });
  if (response.getResponseCode() !== 200) throw new Error('Source HTTP ' + response.getResponseCode());
  // Large official Greenhouse boards (GitLab ~3.9 MB) cannot use the
  // previous 2.5 MB ceiling. Keep a bounded 4.25 MB overall budget.
  var raw = response.getContentText();
  if (raw.length > 4250000) throw new Error('Source response exceeds safety budget');
  return raw;
}

function radarFetchSource_(spec) {
  var url = radarSpecUrl_(spec);
  if (!url) throw new Error('Unsupported approved source');
  try {
    return radarHttp_(url);
  } catch (error) {
    if (spec.adapter !== 'greenhouse' ||
        !/Source response exceeds safety budget/.test(String(error))) throw error;
    // Official Greenhouse jobs list without full descriptions is smaller.
    // Do not silently label missing descriptions as verified role matches.
    return radarHttp_(url.replace('content=true', 'content=false'));
  }
}

function radarSpecUrl_(spec) {
  var account = String(spec.account || '');
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$/.test(account)) return '';
  switch (spec.adapter) {
    case 'greenhouse':
      return 'https://boards-api.greenhouse.io/v1/boards/' + encodeURIComponent(account) + '/jobs?content=true';
    case 'ashby':
      return 'https://api.ashbyhq.com/posting-api/job-board/' + encodeURIComponent(account) + '?includeCompensation=true';
    case 'lever':
      var region = spec.options && spec.options.api_region === 'eu' ? 'api.eu.lever.co' : 'api.lever.co';
      return 'https://' + region + '/v0/postings/' + encodeURIComponent(account) + '?mode=json&limit=100';
    case 'workable':
      return 'https://www.workable.com/api/accounts/' + encodeURIComponent(account) + '?details=true';
    case 'personio':
      return 'https://' + account + '.jobs.personio.com/xml?language=en';
    case 'wordpressjobs':
      return ['development', 'design'].indexOf(account) !== -1 ?
        'https://jobs.wordpress.net/job_category/' + account + '/feed/' : '';
    case 'weworkremotely':
      return account === 'programming' ?
        'https://weworkremotely.com/categories/remote-programming-jobs.rss' : '';
    case 'remoteok':
      return account === 'global' ? 'https://remoteok.com/api' : '';
    case 'himalayas':
      return account === 'global' ?
        'https://himalayas.app/jobs/api/search?q=wordpress&sort=recent&page=1' : '';
    case 'jobicy':
      return account === 'global' ?
        'https://jobicy.com/api/v2/remote-jobs?count=100&tag=wordpress' : '';
    case 'remotive':
      return account === 'global' ?
        'https://remotive.com/api/remote-jobs' : '';
    case 'smartrecruiters':
      return 'https://api.smartrecruiters.com/v1/companies/' +
        encodeURIComponent(account) + '/postings?limit=100&offset=0&destination=PUBLIC';
    default:
      return '';
  }
}

function radarXmlChildText_(item, name) {
  var child = item.getChild(name);
  return child ? child.getText() : '';
}

function radarCandidates_(spec, raw) {
  var jobs = [];
  var adapter = spec.adapter;
  if (['greenhouse', 'ashby', 'lever', 'workable', 'smartrecruiters',
       'remoteok', 'himalayas', 'jobicy', 'remotive'].indexOf(adapter) !== -1) {
    var parsed = JSON.parse(raw);
    if (adapter === 'lever' || adapter === 'remoteok') {
      if (!Array.isArray(parsed)) throw new Error('Feed response is not an array');
      jobs = parsed;
    } else if (adapter === 'smartrecruiters') {
      jobs = parsed && (parsed.content || parsed.postings);
      if (!Array.isArray(jobs)) throw new Error('SmartRecruiters response has no postings');
    } else {
      if (!parsed || !Array.isArray(parsed.jobs)) throw new Error('ATS/feed response has no jobs');
      jobs = parsed.jobs;
    }
  } else {
    var document = XmlService.parse(raw);
    var root = document.getRootElement();
    if (adapter === 'personio') {
      jobs = root.getChildren('position').map(function (item) {
        return {
          id: radarXmlChildText_(item, 'id'),
          title: radarXmlChildText_(item, 'name'),
          url: 'https://' + spec.account + '.jobs.personio.com/job/' +
            encodeURIComponent(radarXmlChildText_(item, 'id')),
          office: radarXmlChildText_(item, 'office'),
          published: radarXmlChildText_(item, 'createdAt')
        };
      });
    } else {
      var channel = root.getChild('channel');
      if (!channel) throw new Error('RSS channel missing');
      jobs = channel.getChildren('item').map(function (item) {
        return {
          id: radarXmlChildText_(item, 'guid'),
          title: radarXmlChildText_(item, 'title'),
          url: radarXmlChildText_(item, 'link'),
          published: radarXmlChildText_(item, 'pubDate'),
          description: radarXmlChildText_(item, 'description')
        };
      });
    }
  }
  return jobs.slice(0, VACATURE_RADAR.maxJobsPerSource).map(function (job) {
    var title, url, jobId, dateHint, location, description, note;
    if (!job || typeof job !== 'object' || (adapter === 'ashby' && job.isListed === false)) return null;
    if (adapter === 'greenhouse') {
      title = job.title; url = job.absolute_url; jobId = job.id;
      dateHint = job.first_published || ''; location = job.location && job.location.name;
      description = job.content; note = 'ATS discovery; first_published when available';
    } else if (adapter === 'ashby') {
      title = job.title; url = job.jobUrl; jobId = job.id;
      dateHint = job.publishedAt || ''; location = job.location;
      description = job.descriptionPlain || job.descriptionHtml;
      if (job.workplaceType && String(job.workplaceType).toLowerCase() !== 'remote') return null;
      note = 'Ashby publishedAt can mean republished; original date unverified';
    } else if (adapter === 'lever') {
      title = job.text; url = job.hostedUrl; jobId = job.id;
      dateHint = ''; location = job.categories && job.categories.location;
      description = job.descriptionPlain || job.description;
      if (job.workplaceType && String(job.workplaceType).toLowerCase() !== 'remote') return null;
      note = 'Lever createdAt is not original employer posting proof';
    } else if (adapter === 'workable') {
      title = job.title; url = job.url || job.shortlink; jobId = job.id || job.shortcode;
      dateHint = job.published_on || ''; location = job.location && job.location.location_str;
      description = job.description || job.full_description;
      note = 'Workable public listing; original date and NL eligibility still unverified';
    } else if (adapter === 'smartrecruiters') {
      title = job.name || job.title; jobId = job.id || job.uuid;
      // The public list may omit a job-specific application link. Never
      // fabricate one from a provider ID: wait for official detail review.
      url = job.applyUrl || '';
      dateHint = job.releasedDate || job.publicationDate || '';
      location = job.location && (job.location.city || job.location.country);
      description = '';
      note = 'SmartRecruiters listing only; review exact official job link';
    } else if (adapter === 'remoteok') {
      title = job.position; url = job.apply_url || job.url; jobId = job.id;
      dateHint = job.date || ''; location = job.location || 'Remote';
      description = job.description || ''; 
      note = 'Remote OK aggregator: official employer role and date unverified';
    } else if (adapter === 'himalayas') {
      title = job.title; url = job.applicationLink; jobId = job.guid;
      dateHint = job.pubDate || '';
      location = Array.isArray(job.locationRestrictions) ?
        job.locationRestrictions.map(function (v) { return typeof v === 'string' ? v : (v && v.name || ''); }).join(', ') :
        'Worldwide';
      description = job.description || ''; 
      note = 'Himalayas discovery only: provider date may differ from first publish';
    } else if (adapter === 'jobicy') {
      title = job.jobTitle; url = job.url; jobId = job.id;
      dateHint = job.pubDate || ''; location = job.jobGeo || 'Remote';
      description = job.jobDescription || '';
      note = 'Jobicy discovery only: employer confirmation required';
    } else if (adapter === 'remotive') {
      title = job.title; url = job.url; jobId = job.id;
      dateHint = job.publication_date || ''; location = job.candidate_required_location || 'Remote';
      description = job.description || '';
      note = 'Remotive delayed discovery feed, employer date unverified';
    } else {
      title = job.title; url = job.url; jobId = job.id;
      dateHint = job.published || ''; location = job.office || '';
      description = job.description || '';
      note = 'RSS/XML discovery date is not independently verified employer original';
    }
    var canonical = radarNormalizeUrl_(String(url || ''));
    if (!title || !canonical) return null;
    return {
      sourceId: spec.source_id,
      sourceType: spec.source_type,
      jobId: String(spec.account || '') + ':' + String(jobId || canonical),
      employer: String(spec.employer || spec.account || ''),
      title: String(title),
      url: canonical,
      publishedHint: String(dateHint || ''),
      location: String(location || ''),
      description: String(description || ''),
      note: note
    };
  }).filter(Boolean);
}

/**
 * Run by the authenticated user's installable 15-minute clock trigger.
 * Return new UNVERIFIED leads, not verified matches or applications.
 */
function radarSourceDue_(spec, nowMs, properties) {
  // Public aggregators update slowly; avoid repeated polling and wasted quota.
  var cadenceMinutes = ({
    'himalayas': 1440, 'remotive': 1440,
    'jobicy': 120, 'remoteok': 60, 'weworkremotely': 60,
    'wordpressjobs': 60, 'smartrecruiters': 60
  })[spec.adapter] || 15;
  var key = 'RADAR_SOURCE_SUCCESS_' + spec.source_id + '_' + spec.account;
  var failAtKey = 'RADAR_SOURCE_FAILURE_AT_' + spec.source_id + '_' + spec.account;
  var failCountKey = 'RADAR_SOURCE_FAILURE_COUNT_' + spec.source_id + '_' + spec.account;
  var last = Number(properties.getProperty(key) || 0);
  var lastFailed = Number(properties.getProperty(failAtKey) || 0);
  var failCount = Math.max(0, Math.min(10, Number(properties.getProperty(failCountKey) || 0)));
  // Exponential backoff up to 4 h for failed feeds; never hot-loop a
  // repeatedly blocked/429 provider. The next healthy run resets the streak.
  var backoff = failCount ? Math.min(240, 15 * Math.pow(2, Math.min(5, failCount - 1))) : 0;
  var coolingDown = !!(failCount && lastFailed && nowMs - lastFailed < backoff * 60000);
  return {
    key: key, failAtKey: failAtKey, failCountKey: failCountKey,
    coolingDown: coolingDown,
    ready: (!last || nowMs - last >= cadenceMinutes * 60000) && !coolingDown
  };
}

function radarRunStatus_(dueCount, failureCount, coolingDownCount) {
  if (failureCount) return 'degraded_source_failures';
  if (coolingDownCount) return 'degraded_source_cooldown';
  return dueCount === 0 ? 'idle_no_sources_due' : 'ok';
}

function radarUpdateDashboard_(radar, active, run) {
  var dashboard = radar.getSheetByName('Dashboard');
  if (!dashboard) return;
  dashboard.getRange('B3').setValue(active ?
    'Actief - Google Apps Script iedere 15 minuten' :
    'Uitgeschakeld - nog geen automatische trigger');
  if (run) {
    dashboard.getRange('B10').setValue(run.at);
    dashboard.getRange('B11').setValue(run.attemptedSources);
    dashboard.getRange('B12').setValue(run.failedSources);
    dashboard.getRange('B13').setValue(run.newLeads);
    dashboard.getRange('B14').setValue(run.inspected);
    dashboard.getRange('B16').setValue(run.alertCandidates || 0);
    var problemSources = (run.failedAccounts || []).concat(run.coolingDownSources || []);
    dashboard.getRange('B17').setValue(problemSources.join(', ') || '-');
    var statusText = {
      idle_no_sources_due: 'In orde - deze ronde geen bronnen aan de beurt',
      degraded_source_cooldown: 'Probleem - bron(nen) wachten op herstart na fout',
      degraded_source_failures: 'Probleem - een of meer broncontroles faalden'
    }[run.status] || run.status;
    dashboard.getRange('B19').setValue(statusText);
    dashboard.getRange('B20').setValue(run.lastSourceFetchAt || 'Nog geen broncontrole');
    dashboard.getRange('B21').setValue(run.configuredSources);
    dashboard.getRange('B22').setValue(run.dueSources);
  }
}

function runVacatureRadar() {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(2000)) return {status: 'busy'};
  try {
    var started = Date.now();
    var register = SpreadsheetApp.openById(VACATURE_RADAR.registerId);
    var radar = SpreadsheetApp.openById(VACATURE_RADAR.radarId);
    var config = radarConfig_(register).config;
    if (config.ingestion_schedule !== VACATURE_RADAR.allowedSchedule) {
      return {status: 'disabled_by_live_config', schedule: config.ingestion_schedule};
    }
    var activeIds = radarSources_(register);
    var permittedFamily = String(config.target_role_families || '').split(',');
    var sourceFile = JSON.parse(radarHttp_(VACATURE_RADAR.specsUrl));
    if (!Array.isArray(sourceFile)) throw new Error('Approved source specification format changed');
    var sourceSpecs = sourceFile.filter(function (spec) {
      var extra = (spec.options || {}).registry_source_id;
      return !!activeIds[spec.source_id] && (!extra || !!activeIds[extra]) &&
        !!radarSpecUrl_(spec);
    });
    var leads = radarTab_(radar, 'Bronvondsten');
    var mapped = radarRecordMap_(leads);
    if (RADAR_LEAD_COLUMNS.some(function (x, i) { return mapped.header[i] !== x; })) {
      throw new Error('Bronvondsten columns differ from approved schema');
    }
    var oldKeys = {}, known = radarKnownUrls_(register, radar);
    mapped.values.forEach(function (row) {
      if (row[0]) oldKeys[String(row[0])] = true;
      var url = radarNormalizeUrl_(String(row[7] || ''));
      if (url) known[url] = true;
    });
    var now = new Date().toISOString();
    var additions = [], alerts = [], attempts = 0, failures = 0, inspected = 0;
    var reviewCounts = {}, failedAccounts = [];
    var props = PropertiesService.getScriptProperties();
    var sourceReadiness = sourceSpecs.map(function (spec) {
      return {spec: spec, state: radarSourceDue_(spec, started, props)};
    });
    var coolingDownSources = sourceReadiness.filter(function (entry) {
      return entry.state.coolingDown;
    }).map(function (entry) {
      return String(entry.spec.source_id) + '/' + String(entry.spec.account);
    });
    var sourceDue = sourceReadiness.filter(function (entry) {
      return entry.state.ready;
    }).map(function (entry) { return entry.spec; });
    var cursor = Math.max(0, Number(props.getProperty('VACATURE_RADAR_CURSOR') || 0) || 0);
    if (sourceDue.length) {
      cursor = cursor % sourceDue.length;
      sourceDue = sourceDue.slice(cursor).concat(sourceDue.slice(0, cursor));
    }
    for (var i = 0; i < sourceDue.length; i++) {
      if (attempts >= VACATURE_RADAR.maxRequests ||
          Date.now() - started > VACATURE_RADAR.maxRuntimeMs) break;
      var spec = sourceDue[i];
      attempts++;
      try {
        var observations = radarCandidates_(spec, radarFetchSource_(spec));
        inspected += observations.length;
        var successKeys = radarSourceDue_(spec, started, props);
        props.setProperty(successKeys.key, String(started));
        props.setProperty(successKeys.failAtKey, '0');
        props.setProperty(successKeys.failCountKey, '0');
        for (var j = 0; j < observations.length; j++) {
          var row = observations[j];
          if (!radarRelevant_(row.title, row.description, permittedFamily)) continue;
          var key = spec.adapter + ':' + row.sourceId + ':' + row.jobId;
          if (oldKeys[key] || known[row.url]) continue;
          oldKeys[key] = true;
          known[row.url] = true;
          var review = radarReview_(row, config, started);
          reviewCounts[review.status] = (reviewCounts[review.status] || 0) + 1;
          var saved = [
            key, now, now, row.sourceId, row.jobId, row.employer, row.title,
            row.url, row.publishedHint, row.location, review.status,
            row.sourceType, row.note + '; ' + review.reason
          ].map(radarSafeCell_);
          additions.push(saved);
          if (review.alert) alerts.push(saved);
          if (additions.length >= VACATURE_RADAR.maxNewRows) break;
        }
      } catch (error) {
        failures++;
        failedAccounts.push(String(spec.source_id) + '/' + String(spec.account));
        var failKeys = radarSourceDue_(spec, started, props);
        var count = Math.min(10, Number(props.getProperty(failKeys.failCountKey) || 0) + 1);
        props.setProperty(failKeys.failAtKey, String(started));
        props.setProperty(failKeys.failCountKey, String(count));
        console.warn('Source failed: ' + String(spec.source_id) + '/' +
          String(spec.account) +
          ' (' + String(error && error.message || error).slice(0, 120) + ')');
      }
      if (additions.length >= VACATURE_RADAR.maxNewRows) break;
    }
    // Move the cursor past the attempted segment, even if a source failed.
    if (sourceDue.length) {
      props.setProperty('VACATURE_RADAR_CURSOR',
        String((cursor + attempts) % sourceDue.length));
    }
    if (additions.length) {
      var needed = leads.getLastRow() + additions.length;
      if (needed > leads.getMaxRows()) {
        leads.insertRowsAfter(leads.getMaxRows(), needed - leads.getMaxRows());
      }
      leads.getRange(leads.getLastRow() + 1, 1, additions.length, RADAR_LEAD_COLUMNS.length)
        .setValues(additions);
      SpreadsheetApp.flush();
      var email = String(props.getProperty('VACATURE_RADAR_ALERT_EMAIL') ||
        Session.getEffectiveUser().getEmail() || '').trim();
      if (alerts.length && email && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
        var summary = alerts.slice(0, 20).map(function (row) {
          return row[5] + ' - ' + row[6] + '\n' + row[7];
        }).join('\n\n');
        try {
          MailApp.sendEmail({
            to: email,
            subject: 'Nieuwe actuele remote-vacaturekandidaten: ' + alerts.length,
            body: 'Nog NIET geverifieerd of sollicitatieklaar.\n\n' + summary +
              '\n\nControleer originele datum, remote vanuit Nederland, talen en employer-ATS.' +
              '\nRadar: https://docs.google.com/spreadsheets/d/' + VACATURE_RADAR.radarId
          });
        } catch (error) {
          console.warn('Notification delivery failed (leads preserved): ' +
            String(error && error.message || error).slice(0, 140));
        }
      }
    }
    if (attempts) props.setProperty('VACATURE_RADAR_LAST_SOURCE_FETCH_AT', now);
    var result = {
      status: radarRunStatus_(sourceDue.length, failures, coolingDownSources.length),
      newLeads: additions.length,
      inspected: inspected, attemptedSources: attempts, failedSources: failures,
      configuredSources: sourceSpecs.length, dueSources: sourceDue.length,
      coolingDownSources: coolingDownSources,
      lastSourceFetchAt: props.getProperty('VACATURE_RADAR_LAST_SOURCE_FETCH_AT') || '',
      alertCandidates: alerts.length, reviewCounts: reviewCounts,
      failedAccounts: failedAccounts,
      incomplete: attempts < sourceDue.length, at: now
    };
    props.setProperty('VACATURE_RADAR_LAST_RUN', JSON.stringify(result));
    radarUpdateDashboard_(radar, true, result);
    return result;
  } finally {
    lock.releaseLock();
  }
}

/**
 * Run ONCE MANUALLY from the bound Apps Script editor.
 * This intentionally changes the prior on-demand-only policy.
 */
function enableVacatureRadar() {
  var register = SpreadsheetApp.openById(VACATURE_RADAR.registerId);
  var radar = SpreadsheetApp.openById(VACATURE_RADAR.radarId);
  radarTab_(radar, 'Nieuwe vacatures');
  var live = radarConfig_(register);
  var current = live.config.ingestion_schedule;
  if (current !== 'on_demand_chatgpt_only' && current !== VACATURE_RADAR.allowedSchedule) {
    throw new Error('Unexpected existing ingestion schedule; do not override another controller');
  }
  var tab = radar.getSheetByName('Bronvondsten');
  if (!tab) {
    tab = radar.insertSheet('Bronvondsten');
    tab.getRange(1, 1, 1, RADAR_LEAD_COLUMNS.length).setValues([RADAR_LEAD_COLUMNS]);
    tab.setFrozenRows(1);
  }
  if (RADAR_LEAD_COLUMNS.some(function (value, i) {
    return tab.getRange(1, i + 1).getValue() !== value;
  })) throw new Error('Bronvondsten header conflict');
  var existing = ScriptApp.getProjectTriggers().filter(function (trigger) {
    return trigger.getHandlerFunction() === 'runVacatureRadar';
  });
  if (existing.length > 1) throw new Error('Multiple radar triggers: inspect before proceeding');
  if (!existing.length) {
    ScriptApp.newTrigger('runVacatureRadar').timeBased().everyMinutes(15).create();
  }
  radarTab_(register, 'Config').getRange(live.rows.ingestion_schedule, 2)
    .setValue(VACATURE_RADAR.allowedSchedule);
  radarUpdateDashboard_(radar, true, null);
  SpreadsheetApp.flush();
  return {status: 'installed', intervalMinutes: 15, usesCloudflare: false};
}

function disableVacatureRadar() {
  ScriptApp.getProjectTriggers().forEach(function (trigger) {
    if (trigger.getHandlerFunction() === 'runVacatureRadar') ScriptApp.deleteTrigger(trigger);
  });
  var register = SpreadsheetApp.openById(VACATURE_RADAR.registerId);
  var live = radarConfig_(register);
  if (live.config.ingestion_schedule === VACATURE_RADAR.allowedSchedule) {
    radarTab_(register, 'Config').getRange(live.rows.ingestion_schedule, 2)
      .setValue('on_demand_chatgpt_only');
  }
  radarUpdateDashboard_(SpreadsheetApp.openById(VACATURE_RADAR.radarId), false, null);
  return {status: 'paused', dataPreserved: true};
}
