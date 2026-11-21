/**
 * Vacature Radar: controlled 30-minute registered-source discovery for a bound Apps Script.
 *
 * No Cloudflare, paid API, applicant submission or canonical Register writes.
 * All discoveries are UNVERIFIED leads in the EXISTING Radar spreadsheet.
 * A user must intentionally run enableVacatureRadar() in the Apps Script editor.
 */
var VACATURE_RADAR = {
  registerId: '1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0',
  radarId: '1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ',
  specsUrl: 'https://raw.githubusercontent.com/Yolol100/vacature-engine/main/ingestion/source-specs.deploy.json',
  allowedSchedule: 'apps_script_30m_registered_sources_public_discovery',
  legacySchedule: 'apps_script_15m_fastlane_and_on_demand_deep',
  maxRequests: 35,
  maxJobsPerSource: 250,
  maxNewRows: 150,
  maxRuntimeMs: 105000,
  publicBatchSize: 12,
  publicMaxHtmlChars: 180000,
  publicMaxCandidates: 100
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
  if (/\b(?:manager|management|director|head of|vp|vice president|chief executive|chief technology|team lead|technical lead)\b/.test(t)) return false;
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
  // Worldwide discovery must not be confused with permission to work from NL.
  // Known employer restrictions are quarantined before any email alert.
  if (/\b(?:w[- ]?2 only|us payroll only|us employees only|us work authorization required|must (?:reside|live|work|be based) in (?:the )?(?:us|u\.?s\.?a?\.?|united states)|no international hiring)\b/.test(geo)) {
    return {status: 'geography_restricted_review', alert: false, reason: 'Employer payroll, residency or work-authorization restriction'};
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
        if (url && !radarSharedCareersUrl_(url)) found[url] = true;
      });
    });
  });
  return found;
}

function radarIdentity_(employer, title) {
  var clean = function (x) { return String(x || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().replace(/\s+/g, ' '); };
  var e = clean(employer), t = clean(title);
  return e && t ? e + '::' + t : '';
}

function radarSharedCareersUrl_(url) {
  var normalized = radarNormalizeUrl_(url);
  if (!normalized) return false;
  var match = normalized.match(/^https:\/\/([^/]+)(\/[^?]*)?(\?.*)?$/i);
  if (!match) return false;
  var host = match[1].toLowerCase();
  var pathname = String(match[2] || '/').replace(/\/+$/, '').toLowerCase() || '/';
  // Employer careers overviews, including ordinary pagination, are not role URLs.
  var listing = /^(?:\/(?:careers?|jobs?|vacatures?|werken-bij|werkenbij|work-with-us|open-positions|openings|join-us|join-our-team|opportunities|about\/careers?|company\/careers?|career\/openings|job-openings))(?:\/(?:page\/\d+|\d+))?$/.test(pathname);
  if (listing) return true;
  // Hosted ATS tenant landing pages; an actual provider job path remains distinct.
  if (/^(?:jobs\.lever\.co|boards\.greenhouse\.io|job-boards\.greenhouse\.io|apply\.workable\.com|jobs\.ashbyhq\.com|careers\.personio\.(?:de|com))$/.test(host)) {
    return /^\/[a-z0-9_-]+(?:\/page\/\d+)?$/i.test(pathname);
  }
  if (/^(?:careers?|jobs?|werkenbij|vacatures?)\./.test(host)) {
    return pathname === '/' || /^\/(?:page\/\d+|\d+)$/.test(pathname);
  }
  return false;
}

// A shared listing URL is never a sufficient job identity. A stable ATS job ID
// distinguishes equal-title openings; when absent, title and employer do.
function radarObservationKey_(spec, row) {
  var provider = String(spec.adapter || '');
  var source = String(row.sourceId || spec.source_id || '');
  var jobId = String(row.jobId || '').trim();
  var shared = radarSharedCareersUrl_(row.url);
  var role = radarIdentity_(row.employer, row.title);
  if (!shared && jobId) return provider + ':' + source + ':' + jobId;
  if (!role) return '';
  // The role disambiguator makes two different roles on one general URL distinct.
  // Keep a real ATS-specific ID so two equal-title job postings stay distinct.
  var explicitId = jobId && jobId !== row.url &&
    !radarSharedCareersUrl_(jobId) ? jobId : '';
  return provider + ':' + source + ':' + (explicitId || radarNormalizeUrl_(row.url)) +
    ':role:' + encodeURIComponent(role).slice(0, 350);
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

function radarHttp_(url, allowRedirects) {
  var response = UrlFetchApp.fetch(url, {
    muteHttpExceptions: true,
    followRedirects: allowRedirects === true,
    headers: {Accept: 'application/json, application/rss+xml, application/xml, text/xml'}
  });
  var status = response.getResponseCode();
  if (status !== 200) {
    var failure = new Error('Source HTTP ' + status);
    if (status === 429 || status === 503) {
      failure.retryAt = radarRetryAfterMs_(response.getAllHeaders(), Date.now());
    }
    throw failure;
  }
  // Large official Greenhouse boards (GitLab ~3.9 MB) cannot use the
  // previous 2.5 MB ceiling. Keep a bounded 4.25 MB overall budget.
  var raw = response.getContentText();
  if (raw.length > 4250000) throw new Error('Source response exceeds safety budget');
  return raw;
}

function radarRetryAfterMs_(headers, nowMs) {
  var key = Object.keys(headers || {}).filter(function (name) {
    return name.toLowerCase() === 'retry-after';
  })[0];
  var value = key && headers[key];
  if (Array.isArray(value)) value = value[0];
  var text = String(value || '').trim();
  if (!text) return 0;
  if (/^\d+$/.test(text)) {
    var delayed = nowMs + Number(text) * 1000;
    return Number.isSafeInteger(delayed) ? delayed : 0;
  }
  var date = Date.parse(text);
  return Number.isFinite(date) && date > nowMs ? date : 0;
}

function radarFetchSource_(spec) {
  var url = radarSpecUrl_(spec);
  if (!url) throw new Error('Unsupported approved source');
  try {
    // Public ATS sources use directly verified HTTPS endpoints; no redirects.
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
      // Direct official widget endpoint; avoid the old 302 hop that caused live cooldowns.
      return 'https://apply.workable.com/api/v1/widget/accounts/' + encodeURIComponent(account) + '?details=true';
    case 'personio':
      return 'https://' + account + '.jobs.personio.com/xml?language=en';
    case 'teamtailor':
      return spec.source_id === 'teamtailor' && account === 'servebolt' &&
        spec.employer === 'Servebolt' &&
        spec.endpoint === 'https://careers.servebolt.com/jobs.rss' &&
        spec.options && spec.options.registry_source_id === 'company-servebolt' ?
        spec.endpoint : '';
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
    if (adapter === 'teamtailor' && /<!DOCTYPE|<!ENTITY/i.test(raw)) {
      throw new Error('Unexpected Teamtailor RSS declaration');
    }
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
          remoteStatus: radarXmlChildText_(item, 'remoteStatus'),
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
      if (!location && Array.isArray(job.locations)) {
        location = job.locations.map(function (entry) {
          return entry && (entry.location_str || entry.country) || '';
        }).filter(Boolean).join(', ');
      }
      if (!location) location = [job.city, job.country].filter(Boolean).join(', ');
      if (job.telecommuting === true && location) location = 'Remote - ' + location;
      if (job.telecommuting === true && !location) location = 'Remote';
      description = job.description || job.full_description;
      note = 'Workable public listing; original date and NL eligibility still unverified';
    } else if (adapter === 'teamtailor') {
      title = job.title; url = job.url;
      var identity = String(url || '').match(/^https:\/\/careers\.servebolt\.com\/jobs\/([1-9]\d*)-[a-z0-9-]+\/?(?:[?#].*)?$/i);
      if (!identity) return null;
      var remoteStatus = String(job.remoteStatus || '').trim().toLowerCase();
      if (/^(hybrid|none|on[ -]?site|temporary)$/.test(remoteStatus)) return null;
      location = /^(fully|fully remote|remote)$/.test(remoteStatus) ? 'Remote' : '';
      jobId = identity[1]; dateHint = job.published || '';
      description = job.description;
      note = 'Employer Teamtailor feed; original date and NL eligibility still unverified';
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
        '';
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
 * Run by the authenticated user's installable 30-minute clock trigger.
 * Return new UNVERIFIED leads, not verified matches or applications.
 */

// All 233 live registered IDs remain authoritative, including discovery portals
// that are not direct job feeds. GET reachability is NOT vacancy verification.
function radarPublicSources_(register) {
  var rows = radarRecordMap_(radarTab_(register, 'Bronnen'));
  return rows.values.filter(function (r) {
    return String(r[rows.names.status] || '').trim().toLowerCase() === 'active';
  }).map(function (r) {
    return {
      id: String(r[rows.names.source_id] || ''),
      name: String(r[rows.names.source_name] || ''),
      type: String(r[rows.names.source_type] || ''),
      url: String(r[rows.names.base_url] || '')
    };
  });
}

function radarPublicRequestUrl_(source, searchIndex) {
  var url = String(source.url || '');
  if (source.id === 'google-jobs') {
    // Google is an optional public discovery route, not an ATS or paid API.
    var queries = [
      'remote WordPress WooCommerce developer jobs',
      'remote Elementor web designer Europe jobs',
      'fully remote frontend web developer WordPress',
      'remote website designer developer Netherlands worldwide'
    ];
    return 'https://www.google.com/search?q=' +
      encodeURIComponent(queries[searchIndex % queries.length]) + '&tbs=qdr:w';
  }
  if (!/^https:\/\/[a-z0-9][a-z0-9.-]*\//i.test(url) ||
      /[\s\r\n\\<>"'@]/.test(url)) return '';
  var host = url.match(/^https:\/\/([^/:?#]+)/i);
  if (!host || /(?:^|\.)(?:localhost|local|internal)$/i.test(host[1]) ||
      /^\d+\.\d+\.\d+\.\d+$/.test(host[1])) return '';
  return url;
}

function radarPublicRoleUrl_(value, baseUrl) {
  var v = String(value || '').replace(/&amp;/gi, '&').trim();
  if (/^\/url\?q=/i.test(v)) {
    v = decodeURIComponent((v.split(/[?&]q=/)[1] || '').split('&')[0]);
  }
  if (v[0] === '/' && v[1] !== '/') {
    var host = String(baseUrl).match(/^(https:\/\/[^/]+)/i);
    if (!host) return '';
    v = host[1] + v;
  }
  if (/^https:\/\/[a-z0-9][a-z0-9.-]*$/i.test(v)) v += '/';
  return radarNormalizeUrl_(v);
}

function radarPublicJobPostings_(raw, source, url) {
  var html = String(raw || '').slice(0, VACATURE_RADAR.publicMaxHtmlChars);
  var result = [], seen = {}, scripts = /<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi, match;
  function visit(item, depth) {
    if (!item || depth > 5 || result.length >= 8) return;
    if (Array.isArray(item)) {
      item.slice(0, 60).forEach(function (x) { visit(x, depth + 1); });
      return;
    }
    if (typeof item !== 'object') return;
    var ty = item['@type'], jobPosting = ty === 'JobPosting' ||
      Array.isArray(ty) && ty.indexOf('JobPosting') !== -1;
    if (jobPosting) {
      var link = radarPublicRoleUrl_(item.url || '', url);
      var title = String(item.title || '').trim().slice(0, 180);
      var details = String(item.description || '').slice(0, 4000);
      var remote = /TELECOMMUTE/i.test(String(item.jobLocationType || '')) ||
        /\b(fully remote|100% remote|work from anywhere)\b/i.test(details);
      var region = item.applicantLocationRequirements;
      if (Array.isArray(region)) region = region[0];
      var location = region && (region.name || region.address && region.address.addressCountry) || '';
      if (remote) location = 'Remote' + (location ? ' - ' + String(location) : '');
      var organisation = item.hiringOrganization || {};
      var employer = String(organisation.name || source.name || '').slice(0, 150);
      if (link && title && remote && !seen[link]) {
        seen[link] = true;
        result.push({
          sourceId: source.id, sourceType: source.type, jobId: link,
          employer: employer, title: title, url: link,
          publishedHint: String(item.datePosted || ''),
          location: location, description: details,
          note: 'Public JobPosting schema only; employer/ATS and NL eligibility unverified'
        });
      }
    }
    if (item['@graph']) visit(item['@graph'], depth + 1);
  }
  while ((match = scripts.exec(html)) && result.length < 8) {
    if (!/type\s*=\s*['"]application\/ld\+json['"]/i.test(match[1])) continue;
    try { visit(JSON.parse(match[2].trim()), 0); } catch (e) { /* invalid data are not jobs */ }
  }
  return result;
}

function radarPublicRemoteLinks_(raw, source, url) {
  // Link text itself must say both a relevant role and remote: do not
  // infer a remote job from a general careers page or a Google query.
  var html = String(raw || '').slice(0, VACATURE_RADAR.publicMaxHtmlChars);
  var matches = /<a\b[^>]*href\s*=\s*["']([^"'<>]{3,1200})["'][^>]*>([\s\S]{0,400}?)<\/a\s*>/gi;
  var result = [], seen = {}, m;
  while ((m = matches.exec(html)) && result.length < 5) {
    var title = m[2].replace(/<[^>]+>/g, ' ').replace(/&(?:nbsp|amp);/gi, ' ')
      .replace(/\s+/g, ' ').trim().slice(0, 180);
    if (!/\bremote\b/i.test(title) ||
        !/\b(?:wordpress|woocommerce|elementor|gutenberg|web\s?design|web\s?develop|front.?end|website)\b/i.test(title)) continue;
    var link = radarPublicRoleUrl_(m[1], url);
    if (!link || seen[link] || /^https:\/\/(?:www\.)?google\./i.test(link)) continue;
    // Listing overview URLs are not evidence of a distinct opening.
    if (radarSharedCareersUrl_(link)) continue;
    seen[link] = true;
    result.push({
      sourceId: source.id, sourceType: source.type, jobId: link,
      employer: source.name, title: title, url: link,
      publishedHint: '', location: 'Remote', description: '',
      note: 'Remote link-text discovery only; official role/date/NL eligibility unverified'
    });
  }
  return result;
}

function radarPublicHealthSheet_(radar, runRows) {
  var name = 'Broncontrole 30m';
  var tab = radar.getSheetByName(name) || radar.insertSheet(name);
  var header = ['source_id','source_type','source_url','attempted_utc',
    'http_result','remote_candidate_links','coverage_note'];
  if (tab.getLastRow() && header.some(function (x, i) {
    return String(tab.getRange(1, i + 1).getValue() || '') !== x;
  })) throw new Error('30-minute source log header conflict');
  if (tab.getMaxRows() < runRows.length + 1) {
    tab.insertRowsAfter(tab.getMaxRows(), runRows.length + 1 - tab.getMaxRows());
  }
  if (!tab.getLastRow()) {
    tab.getRange(1, 1, 1, header.length).setValues([header]);
    tab.setFrozenRows(1);
  }
  if (runRows.length) {
    tab.getRange(2, 1, runRows.length, header.length).setValues(runRows);
  }
}

// Conservative HTTP-only discovery: no browser JS execution, no paid search,
// no CAPTCHA bypass. Every source is given an honest per-round outcome.
function radarSweepPublicRegistry_(register, radar, props, started, known, oldKeys, family, config) {
  var sources = radarPublicSources_(register);
  var rows = {}, additions = [], attempts = 0, errors = 0, googleStatus = 'not_attempted';
  var searchIndex = Math.max(0, Number(props.getProperty('VACATURE_RADAR_GOOGLE_CURSOR') || 0) || 0);
  var cursor = Math.max(0, Number(props.getProperty('VACATURE_RADAR_PUBLIC_CURSOR') || 0) || 0);
  if (sources.length) cursor %= sources.length;
  var rotated = sources.slice(cursor).concat(sources.slice(0, cursor));
  var now = new Date().toISOString();
  var size = VACATURE_RADAR.publicBatchSize;
  for (var start = 0; start < rotated.length; start += size) {
    if (Date.now() - started >= VACATURE_RADAR.maxRuntimeMs) break;
    var batch = rotated.slice(start, start + size), req = [], queued = [];
    batch.forEach(function (source) {
      var link = radarPublicRequestUrl_(source, searchIndex);
      var cooldown = Number(props.getProperty('RADAR_PUBLIC_RETRY_' + source.id) || 0);
      if (!link) {
        rows[source.id] = [source.id,source.type,source.url,'','invalid_url',0,
          'No safe public HTTPS endpoint'];
      } else if (cooldown > started) {
        rows[source.id] = [source.id,source.type,source.url,'','cooldown',0,
          'Do not retry before ' + new Date(cooldown).toISOString()];
      } else {
        queued.push({source:source,link:link});
        req.push({url:link,method:'get',followRedirects:false,
          muteHttpExceptions:true,headers:{Accept:'text/html, application/ld+json'}});
      }
    });
    if (!queued.length) continue;
    attempts += queued.length;
    var responses;
    try { responses = UrlFetchApp.fetchAll(req); } catch (error) {
      errors += queued.length;
      queued.forEach(function (entry) {
        rows[entry.source.id] = [entry.source.id,entry.source.type,entry.source.url,now,
          'request_batch_failed',0,'Network or script provider restricted batch'];
      });
      continue;
    }
    queued.forEach(function (entry, i) {
      var source = entry.source, status = 0, count = 0, note = '';
      try {
        var response = responses[i], http = response.getResponseCode();
        status = http;
        if (http === 200) {
          var body = response.getContentText().slice(0,VACATURE_RADAR.publicMaxHtmlChars);
          var candidateRows = radarPublicJobPostings_(body, source, entry.link)
            .concat(radarPublicRemoteLinks_(body, source, entry.link));
          candidateRows.forEach(function (job) {
            if (additions.length >= VACATURE_RADAR.publicMaxCandidates ||
                !radarRelevant_(job.title,job.description,family)) return;
            var review = radarReview_(job,config,started);
            if (review.status === 'not_fully_remote_review' ||
                review.status === 'geography_restricted_review') return;
            var key = radarObservationKey_({adapter:source.id === 'google-jobs' ?
              'google_public' : 'public_html', source_id:source.id},job);
            var normalized = radarNormalizeUrl_(job.url);
            if (!key || oldKeys[key] || (!radarSharedCareersUrl_(job.url) && known[normalized])) return;
            oldKeys[key] = true;
            if (!radarSharedCareersUrl_(job.url)) known[normalized] = true;
            additions.push([
              key,now,now,job.sourceId,job.jobId,job.employer,job.title,
              job.url,job.publishedHint,job.location,review.status,
              job.sourceType,job.note + '; ' + review.reason
            ].map(radarSafeCell_));
            count++;
          });
          note = 'Reachable public HTML; no JS rendering; no complete site vacancy audit';
        } else {
          errors++;
          note = 'Access limited or HTTP error; no vacancy count asserted';
          if (http === 429 || http === 403 || http === 401) {
            var retryAt = http === 429 ?
              radarRetryAfterMs_(response.getAllHeaders(),started) : 0;
            props.setProperty('RADAR_PUBLIC_RETRY_' + source.id,
              String(Math.max(started + (http === 429 ? 3600000 : 12 * 3600000),retryAt)));
          }
        }
      } catch (error) {
        errors++; note = 'HTML parsing or fetch response unavailable';
      }
      var outcome = 'http_' + (status || 'error');
      if (source.id === 'google-jobs') googleStatus = outcome +
        (count ? '_with_candidates' : '_no_qualified_links');
      rows[source.id] = [source.id,source.type,source.url,now,outcome,count,note];
    });
  }
  var checkedIds = Object.keys(rows), attemptCount = checkedIds.filter(function (id) {
    return !!rows[id][3];
  }).length;
  var pending = sources.filter(function (source) { return !rows[source.id]; });
  pending.forEach(function (source) {
    rows[source.id] = [source.id,source.type,source.url,'','time_budget_not_reached',0,
      'Coverage incomplete; retry on next 30-minute run'];
  });
  var output = sources.map(function (source) { return rows[source.id]; });
  radarPublicHealthSheet_(radar,output);
  if (sources.some(function (source) {return source.id === 'google-jobs';})) {
    props.setProperty('VACATURE_RADAR_GOOGLE_CURSOR',String(searchIndex + 1));
  }
  props.setProperty('VACATURE_RADAR_PUBLIC_CURSOR',
    String(sources.length ? (cursor + start) % sources.length : 0));
  return {total:sources.length,attempted:attemptCount,errors:errors,
    pending:pending.length,added:additions,googleStatus:googleStatus};
}

function radarEnsure30MinuteTrigger_(properties) {
  var marker = 'VACATURE_RADAR_TRIGGER_30M_V1';
  var triggers = ScriptApp.getProjectTriggers().filter(function (trigger) {
    return trigger.getHandlerFunction() === 'runVacatureRadar';
  });
  if (triggers.length > 1) throw new Error('Multiple Radar triggers: no automatic migration');
  if (properties.getProperty(marker) === 'done' && triggers.length === 1)
    return '30m_already_configured';
  if (triggers.length === 0) throw new Error('No existing Radar trigger; install manually');
  var replacement = ScriptApp.newTrigger('runVacatureRadar').timeBased()
    .everyMinutes(30).create();
  try {
    ScriptApp.deleteTrigger(triggers[0]);
    properties.setProperty(marker,'done');
  } catch (error) {
    try { ScriptApp.deleteTrigger(replacement); } catch (cleanupError) {}
    throw error;
  }
  return '30m_trigger_migrated';
}

function radarSourceDue_(spec, nowMs, properties) {
  // Public aggregators update slowly; avoid repeated polling and wasted quota.
  var cadenceMinutes = ({
    'himalayas': 1440, 'remotive': 1440,
    'jobicy': 120, 'remoteok': 60, 'weworkremotely': 60,
    'wordpressjobs': 60, 'smartrecruiters': 60, 'teamtailor': 60
  })[spec.adapter] || 15;
  var key = 'RADAR_SOURCE_SUCCESS_' + spec.source_id + '_' + spec.account;
  var failAtKey = 'RADAR_SOURCE_FAILURE_AT_' + spec.source_id + '_' + spec.account;
  var failCountKey = 'RADAR_SOURCE_FAILURE_COUNT_' + spec.source_id + '_' + spec.account;
  var retryAtKey = 'RADAR_SOURCE_RETRY_AT_' + spec.source_id + '_' + spec.account;
  var last = Number(properties.getProperty(key) || 0);
  var lastFailed = Number(properties.getProperty(failAtKey) || 0);
  var failCount = Math.max(0, Math.min(10, Number(properties.getProperty(failCountKey) || 0)));
  // Exponential backoff up to 4 h for failed feeds; never hot-loop a
  // repeatedly blocked/429 provider. The next healthy run resets the streak.
  var backoff = failCount ? Math.min(240, 15 * Math.pow(2, Math.min(5, failCount - 1))) : 0;
  var retryAt = Number(properties.getProperty(retryAtKey) || 0);
  var coolingDown = retryAt > nowMs ||
    !!(failCount && lastFailed && nowMs - lastFailed < backoff * 60000);
  return {
    key: key, failAtKey: failAtKey, failCountKey: failCountKey, retryAtKey: retryAtKey,
    coolingDown: coolingDown,
    ready: (!last || nowMs - last >= cadenceMinutes * 60000) && !coolingDown
  };
}

function radarRunStatus_(dueCount, failureCount, coolingDownCount) {
  if (failureCount) return 'degraded_source_failures';
  if (coolingDownCount) return 'degraded_source_cooldown';
  return dueCount === 0 ? 'idle_no_sources_due' : 'ok';
}


// Read-only observability for the two approved Workable sources.
// Never override Retry-After or a source's exponential backoff.
function radarWorkableHealth_(properties, nowMs) {
  return ['awesomemotive', 'humanmade'].map(function (account) {
    var spec = {adapter: 'workable', source_id: 'workable', account: account};
    var state = radarSourceDue_(spec, nowMs, properties);
    var lastSuccess = Number(properties.getProperty(state.key) || 0);
    var lastFailure = Number(properties.getProperty(state.failAtKey) || 0);
    var failCount = Math.max(0, Math.min(10,
      Number(properties.getProperty(state.failCountKey) || 0)));
    var backoffMs = failCount ?
      Math.min(240, 15 * Math.pow(2, Math.min(5, failCount - 1))) * 60000 : 0;
    var nextRetry = Math.max(Number(properties.getProperty(state.retryAtKey) || 0),
      lastFailure && failCount ? lastFailure + backoffMs : 0);
    var lastError = String(properties.getProperty('RADAR_SOURCE_ERROR_workable_' + account) || '');
    var observations = Number(properties.getProperty('RADAR_SOURCE_OBSERVATIONS_workable_' + account) || 0);
    var message;
    if (lastSuccess && lastSuccess > lastFailure) {
      message = 'SUCCES ' + new Date(lastSuccess).toISOString() +
        ' | ingelezen: ' + observations;
    } else if (lastFailure) {
      message = 'FOUT ' + new Date(lastFailure).toISOString() +
        ' | ' + (lastError || 'Details nog niet gelogd');
    } else {
      message = 'Nog geen succesvolle Apps Script-opvraag bekend';
    }
    if (state.coolingDown) {
      message += ' | herstart niet eerder dan ' + new Date(nextRetry).toISOString();
    }
    return ['Workable / ' + account, message];
  });
}

function radarProductionId_(id, config) {
  var value = String(id || '').trim();
  var prefixes = String(config.nonproduction_vacancy_id_prefixes || 'test:,history:')
    .split(',').map(function (prefix) { return prefix.trim().toLowerCase(); }).filter(Boolean);
  return value && !prefixes.some(function (prefix) {
    return value.toLowerCase().indexOf(prefix) === 0;
  }) ? value : '';
}

function radarApplicationMetrics_(register, config) {
  config = config || {};
  var ready = new Set(), submitted = new Set(), interviews = new Set(), closed = new Set();
  var applications = radarRecordMap_(radarTab_(register, 'Applications'));
  applications.values.forEach(function (row) {
    var id = radarProductionId_(row[applications.names.vacancy_id], config);
    if (!id) return;
    var status = String(row[applications.names.status] || '').trim().toLowerCase();
    if (status === 'prepared_cv_ready') ready.add(id);
    if (status === 'submitted' || status === 'applied') submitted.add(id);
    if (status === 'interview') interviews.add(id);
    if (['closed', 'rejected', 'declined', 'withdrawn'].indexOf(status) !== -1) closed.add(id);
  });
  var events = radarRecordMap_(radarTab_(register, 'ApplicationEvents'));
  var replies = new Set();
  events.values.forEach(function (row) {
    var id = radarProductionId_(row[events.names.vacancy_id], config);
    if (!id) return;
    var type = String(row[events.names.event_type] || '').trim().toLowerCase();
    if (type === 'submitted') submitted.add(id);
    if (type === 'interview') interviews.add(id);
    var eventId = String(row[events.names.event_id] || '');
    if (type === 'employer_reply' && eventId) replies.add(eventId);
  });
  var vacancies = radarRecordMap_(radarTab_(register, 'Vacatures'));
  var closedVacancies = new Set();
  vacancies.values.forEach(function (row) {
    var id = radarProductionId_(row[vacancies.names.vacancy_id], config);
    if (id && String(row[vacancies.names.status] || '').trim().toLowerCase() === 'closed') {
      closedVacancies.add(id);
    }
  });
  return {
    readyPackages: ready.size,
    submitted: submitted.size,
    replies: replies.size,
    interviews: interviews.size,
    closedOrRejected: closed.size,
    closedVacancies: closedVacancies.size
  };
}

function radarUpdateDashboard_(radar, active, run, applicationMetrics) {
  var dashboard = radar.getSheetByName('Dashboard');
  if (!dashboard) return;
  dashboard.getRange('B3').setValue(active ?
    (run && /^(?:30m_trigger_migrated|30m_already_configured)$/.test(run.triggerState || '') ?
      'Actief - Google Apps Script iedere 30 minuten' :
      'Actief - triggerinterval nog te verifieren') :
    'Uitgeschakeld - nog geen automatische trigger');
  if (run) {
    dashboard.getRange('A10').setValue('Laatste uitvoering (UTC)');
    dashboard.getRange('B10').setValue(run.at);
    // An idle trigger is not a source scan. Keep the last real round's counts.
    if (run.attemptedSources > 0) {
      dashboard.getRange('B11').setValue(run.attemptedSources);
      dashboard.getRange('B12').setValue(run.failedSources);
      dashboard.getRange('B13').setValue(run.newLeads);
      dashboard.getRange('B14').setValue(run.inspected);
      dashboard.getRange('B16').setValue(run.alertCandidates || 0);
      var problemSources = run.failedAccounts || [];
      dashboard.getRange('B17').setValue(problemSources.join(', ') || '-');
      dashboard.getRange('B20').setValue(run.lastSourceFetchAt || 'Nog geen broncontrole');
      dashboard.getRange('B22').setValue(run.dueSources);
    }
    var statusText = {
      idle_no_sources_due: 'Geen bronnen aan de beurt bij deze uitvoering',
      public_partial: 'Onvolledig - niet alle actieve bronnen gecontroleerd',
      public_restricted: 'Beperkt - openbare bronnen blokkeren verzoeken',
      degraded_source_cooldown: 'Probleem - bron(nen) wachten op herstart na fout',
      degraded_source_failures: 'Probleem - een of meer broncontroles faalden'
    }[run.status] || run.status;
    dashboard.getRange('B19').setValue(statusText);
    dashboard.getRange('B21').setValue(run.configuredSources);
    if (run.publicSources) {
      dashboard.getRange('A52:B58').setValues([
        ['Geregistreerde actieve bronnen',run.publicSources.total],
        ['Openbare bron-URL checks',run.publicSources.attempted],
        ['Niet binnen budget verwerkt',run.publicSources.pending],
        ['Openbare bronfouten / beperkte toegang',run.publicSources.errors],
        ['Google publieke zoekroute',run.publicSources.googleStatus],
        ['Javascript-browserpagina\'s','Niet automatisch gerenderd door Apps Script'],
        ['30-minuten trigger',run.triggerState || 'onbekend']
      ]);
    }
    if (Array.isArray(run.workableHealth)) {
      dashboard.getRange('A50:B51').setValues(run.workableHealth);
    }
    dashboard.getRange('A23').setValue('Sollicitatiepakketten klaar');
    dashboard.getRange('A24').setValue('Ingediende sollicitaties');
    dashboard.getRange('A25').setValue('Werkgeversreacties');
    dashboard.getRange('A26').setValue('Sollicitaties met gesprek');
    dashboard.getRange('A27').setValue('Afgesloten of afgewezen sollicitaties');
    var metrics = applicationMetrics || {};
    dashboard.getRange('B23').setValue(metrics.readyPackages || 0);
    dashboard.getRange('B24').setValue(metrics.submitted || 0);
    dashboard.getRange('B25').setValue(metrics.replies || 0);
    dashboard.getRange('B26').setValue(metrics.interviews || 0);
    dashboard.getRange('B27').setValue(metrics.closedOrRejected || 0);
    dashboard.getRange('A28:B34').setValues([
      ['Laatste succesvolle broncontrole (UTC)', run.lastSourceSuccessAt || 'Nog niet gemeten'],
      ['Geslaagde bronnen bij laatste bronronde', run.attemptedSources > 0 ?
        run.attemptedSources - run.failedSources : dashboard.getRange('B29').getValue()],
      ['Laatste automatische uitvoering (UTC)', run.lastTriggerAt || 'Nog niet gemeten'],
      ['Bronnen in wachttijd', (run.coolingDownSources || []).join(', ') || '-'],
      ['Oudere leads volgens bronhint', run.historicalLeads || 0],
      ['Gesloten vacatures in Register', metrics.closedVacancies || 0],
      ['Type laatste uitvoering', run.triggered ? 'Automatisch' : 'Handmatig']
    ]);
  }
}

// One-time migration for stale cooldowns caused by the former Workable 302 API.
// Only the two verified direct-widget sources are reset. Subsequent real
// HTTP failures immediately regain normal bounded backoff.
function radarMigrateWorkableDirectEndpoint_(specs, props) {
  var marker = 'VACATURE_RADAR_WORKABLE_DIRECT_V1';
  if (props.getProperty(marker) === 'done') return false;
  specs.forEach(function (spec) {
    if (spec.adapter !== 'workable' ||
        ['awesomemotive', 'humanmade'].indexOf(spec.account) === -1) return;
    var prefix = spec.source_id + '_' + spec.account;
    props.deleteProperty('RADAR_SOURCE_FAILURE_AT_' + prefix);
    props.deleteProperty('RADAR_SOURCE_FAILURE_COUNT_' + prefix);
    props.deleteProperty('RADAR_SOURCE_RETRY_AT_' + prefix);
  });
  props.setProperty(marker, 'done');
  return true;
}

function runVacatureRadar(event) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(2000)) return {status: 'busy'};
  try {
    var started = Date.now();
    var register = SpreadsheetApp.openById(VACATURE_RADAR.registerId);
    var radar = SpreadsheetApp.openById(VACATURE_RADAR.radarId);
    var config = radarConfig_(register).config;
    // Fail closed on policy drift: the skill and the live Register require NL-only.
    if (String(config.allowed_work_locations || '').trim().toUpperCase() !== 'NL' ||
        String(config.remote_scope || '').trim().toLowerCase() !== 'worldwide') {
      throw new Error('Regional policy drift: worldwide discovery, NL execution required');
    }
    if (String(config.allowed_listing_languages || '').replace(/\s/g, '').toLowerCase() !== 'nl,en') {
      throw new Error('Language policy drift: NL and EN listings only');
    }
    if ([VACATURE_RADAR.allowedSchedule, VACATURE_RADAR.legacySchedule]
        .indexOf(config.ingestion_schedule) === -1) {
      return {status: 'disabled_by_live_config', schedule: config.ingestion_schedule};
    }
    var activeIds = radarSources_(register);
    var fullMode = config.ingestion_schedule === VACATURE_RADAR.allowedSchedule;
    var permittedFamily = String(config.target_role_families || '').split(',');
    var sourceFile = JSON.parse(radarHttp_(VACATURE_RADAR.specsUrl));
    if (!Array.isArray(sourceFile)) throw new Error('Approved source specification format changed');
    var sourceSpecs = sourceFile.filter(function (spec) {
      var extra = (spec.options || {}).registry_source_id;
      var listingLang = String(spec.listing_language || '').toLowerCase();
      return !!activeIds[spec.source_id] && (!extra || !!activeIds[extra]) &&
        (!listingLang || listingLang === 'nl' || listingLang === 'en') && !!radarSpecUrl_(spec);
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
      if (url && !radarSharedCareersUrl_(url)) known[url] = true;
    });
    var now = new Date().toISOString();
    var additions = [], alerts = [], attempts = 0, failures = 0, inspected = 0;
    var reviewCounts = {}, failedAccounts = [];
    var props = PropertiesService.getScriptProperties();
    var triggerState = 'legacy_15m';
    if (fullMode && event && event.triggerUid) {
      try { triggerState = radarEnsure30MinuteTrigger_(props); }
      catch (triggerError) {
        triggerState = 'migration_blocked';
        console.warn('30-minute trigger migration failed: ' + String(triggerError).slice(0,140));
      }
    }
    radarMigrateWorkableDirectEndpoint_(sourceSpecs, props);
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
        console.info('Source succeeded: ' + spec.source_id + '/' +
          spec.account + ' (' + observations.length + ' observations)');
        var successKeys = radarSourceDue_(spec, started, props);
        props.setProperty(successKeys.key, String(started));
        props.setProperty(successKeys.failAtKey, '0');
        props.setProperty(successKeys.failCountKey, '0');
        props.deleteProperty(successKeys.retryAtKey);
        if (spec.adapter === 'workable' &&
            ['awesomemotive', 'humanmade'].indexOf(spec.account) !== -1) {
          props.deleteProperty('RADAR_SOURCE_ERROR_workable_' + spec.account);
          props.setProperty('RADAR_SOURCE_OBSERVATIONS_workable_' + spec.account,
            String(observations.length));
        }
        for (var j = 0; j < observations.length; j++) {
          var row = observations[j];
          if (!radarRelevant_(row.title, row.description, permittedFamily)) continue;
          var key = radarObservationKey_(spec, row);
          if (!key) continue;
          // Normalise first: tracking and trailing slashes must not create repeats.
          var normalizedUrl = radarNormalizeUrl_(row.url);
          var sharedListing = radarSharedCareersUrl_(row.url);
          if (oldKeys[key] || (!sharedListing && known[normalizedUrl])) continue;
          oldKeys[key] = true;
          if (!sharedListing) known[normalizedUrl] = true;
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
        props.setProperty(failKeys.failAtKey, String(Date.now()));
        if (error && error.retryAt > Date.now()) {
          props.setProperty(failKeys.retryAtKey, String(error.retryAt));
        }
        props.setProperty(failKeys.failCountKey, String(count));
        if (spec.adapter === 'workable' &&
            ['awesomemotive', 'humanmade'].indexOf(spec.account) !== -1) {
          props.setProperty('RADAR_SOURCE_ERROR_workable_' + spec.account,
            String(error && error.message || error).slice(0, 120));
        }
        console.warn('Source failed: ' + String(spec.source_id) + '/' +
          String(spec.account) +
          ' (' + String(error && error.message || error).slice(0, 120) + ')');
      }
      if (additions.length >= VACATURE_RADAR.maxNewRows) break;
    }
    var publicSources = null;
    if (fullMode) {
      var publicScan = radarSweepPublicRegistry_(register,radar,props,started,
        known,oldKeys,permittedFamily,config);
      if (publicScan.added.length) {
        additions = additions.concat(publicScan.added).slice(0,VACATURE_RADAR.maxNewRows);
      }
      publicSources = {total: publicScan.total,attempted: publicScan.attempted,
        errors: publicScan.errors,pending: publicScan.pending,
        candidates: publicScan.added.length,googleStatus: publicScan.googleStatus};
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
    if (attempts > failures) props.setProperty('VACATURE_RADAR_LAST_SOURCE_SUCCESS_AT', now);
    var triggered = !!(event && event.triggerUid);
    if (triggered) props.setProperty('VACATURE_RADAR_LAST_TRIGGER_AT', now);
    var historicalLeads = mapped.values.concat(additions).filter(function (row) {
      return row[10] === 'historical_review';
    }).length;
    var result = {
      status: fullMode && publicSources && publicSources.pending > 0 ? 'public_partial' :
        fullMode && publicSources && publicSources.errors > 0 ? 'public_restricted' :
        radarRunStatus_(sourceDue.length, failures, coolingDownSources.length),
      newLeads: additions.length,
      inspected: inspected, attemptedSources: attempts, failedSources: failures,
      configuredSources: sourceSpecs.length, dueSources: sourceDue.length,
      publicSources: publicSources,triggerState:triggerState,
      coolingDownSources: coolingDownSources,
      workableHealth: radarWorkableHealth_(props, started),
      lastSourceFetchAt: props.getProperty('VACATURE_RADAR_LAST_SOURCE_FETCH_AT') || '',
      lastSourceSuccessAt: props.getProperty('VACATURE_RADAR_LAST_SOURCE_SUCCESS_AT') || '',
      lastTriggerAt: props.getProperty('VACATURE_RADAR_LAST_TRIGGER_AT') || '',
      triggered: triggered, historicalLeads: historicalLeads,
      alertCandidates: alerts.length, reviewCounts: reviewCounts,
      failedAccounts: failedAccounts,
      incomplete: attempts < sourceDue.length, at: now
    };
    props.setProperty('VACATURE_RADAR_LAST_RUN', JSON.stringify(result));
    radarUpdateDashboard_(radar, true, result, radarApplicationMetrics_(register, config));
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
  if (['on_demand_chatgpt_only',VACATURE_RADAR.allowedSchedule,
       VACATURE_RADAR.legacySchedule].indexOf(current) === -1) {
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
    ScriptApp.newTrigger('runVacatureRadar').timeBased().everyMinutes(30).create();
    PropertiesService.getScriptProperties().setProperty('VACATURE_RADAR_TRIGGER_30M_V1','done');
  } else {
    radarEnsure30MinuteTrigger_(PropertiesService.getScriptProperties());
  }
  radarTab_(register, 'Config').getRange(live.rows.ingestion_schedule, 2)
    .setValue(VACATURE_RADAR.allowedSchedule);
  radarUpdateDashboard_(radar, true, null);
  SpreadsheetApp.flush();
  return {status: 'installed', intervalMinutes: 30, usesCloudflare: false};
}

function disableVacatureRadar() {
  ScriptApp.getProjectTriggers().forEach(function (trigger) {
    if (trigger.getHandlerFunction() === 'runVacatureRadar') ScriptApp.deleteTrigger(trigger);
  });
  var register = SpreadsheetApp.openById(VACATURE_RADAR.registerId);
  var live = radarConfig_(register);
  if ([VACATURE_RADAR.allowedSchedule,VACATURE_RADAR.legacySchedule]
      .indexOf(live.config.ingestion_schedule) !== -1) {
    radarTab_(register, 'Config').getRange(live.rows.ingestion_schedule, 2)
      .setValue('on_demand_chatgpt_only');
  }
  radarUpdateDashboard_(SpreadsheetApp.openById(VACATURE_RADAR.radarId), false, null);
  return {status: 'paused', dataPreserved: true};
}
