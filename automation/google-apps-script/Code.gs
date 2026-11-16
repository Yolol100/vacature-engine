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
  var d = String(description || '').slice(0, 10000).toLowerCase();
  var wordpress = /\bwordpress\b|\bwoocommerce\b|\belementor\b|\bgutenberg\b|\bwpml\b|\bacf\b/.test(t) ||
    (/\bdeveloper\b|\bengineer\b|\bdesigner\b|\bsupport\b|\bweb\b|\bfrontend\b|\bfront.end\b|\bphp\b/.test(t) &&
     /\bwordpress\b|\bwoocommerce\b|\belementor\b|\bgutenberg\b/.test(d));
  if (wordpress) return true;
  return family.indexOf('web_design_development') !== -1 &&
    /\bweb\s?designer\b|\bfront.?end\b|\bwebsite\b|\bweb developer\b|\bweb ux\b/.test(t);
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
  var raw = response.getContentText();
  if (raw.length > 2500000) throw new Error('Source response exceeds safety budget');
  return raw;
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
  if (['greenhouse', 'ashby', 'lever', 'workable'].indexOf(adapter) !== -1) {
    var parsed = JSON.parse(raw);
    if (adapter === 'lever') {
      if (!Array.isArray(parsed)) throw new Error('Lever response is not an array');
      jobs = parsed;
    } else {
      if (!parsed || !Array.isArray(parsed.jobs)) throw new Error('ATS response has no jobs');
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
    var additions = [], attempts = 0, failures = 0, inspected = 0;
    for (var i = 0; i < sourceSpecs.length; i++) {
      if (attempts >= VACATURE_RADAR.maxRequests ||
          Date.now() - started > VACATURE_RADAR.maxRuntimeMs) break;
      var spec = sourceSpecs[i];
      attempts++;
      try {
        var observations = radarCandidates_(spec, radarHttp_(radarSpecUrl_(spec)));
        inspected += observations.length;
        for (var j = 0; j < observations.length; j++) {
          var row = observations[j];
          if (!radarRelevant_(row.title, row.description, permittedFamily)) continue;
          var key = spec.adapter + ':' + row.sourceId + ':' + row.jobId;
          if (oldKeys[key] || known[row.url]) continue;
          oldKeys[key] = true;
          known[row.url] = true;
          additions.push([
            key, now, now, row.sourceId, row.jobId, row.employer, row.title,
            row.url, row.publishedHint, row.location, 'needs_official_review',
            row.sourceType, row.note
          ].map(radarSafeCell_));
          if (additions.length >= VACATURE_RADAR.maxNewRows) break;
        }
      } catch (error) {
        failures++;
        console.warn('Source failed: ' + String(spec.source_id) +
          ' (' + String(error && error.message || error).slice(0, 120) + ')');
      }
      if (additions.length >= VACATURE_RADAR.maxNewRows) break;
    }
    if (additions.length) {
      leads.getRange(leads.getLastRow() + 1, 1, additions.length, RADAR_LEAD_COLUMNS.length)
        .setValues(additions);
      SpreadsheetApp.flush();
      var email = String(PropertiesService.getScriptProperties()
        .getProperty('VACATURE_RADAR_ALERT_EMAIL') || '').trim();
      if (email && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
        var summary = additions.slice(0, 20).map(function (row) {
          return row[5] + ' - ' + row[6] + '\n' + row[7];
        }).join('\n\n');
        MailApp.sendEmail({
          to: email,
          subject: 'Nieuwe vacaturekandidaten ter controle: ' + additions.length,
          body: 'Nog NIET geverifieerd of sollicitatieklaar.\n\n' + summary +
            '\n\nControleer originele datum, remote vanuit Nederland, talen en employer-ATS.' +
            '\nRadar: https://docs.google.com/spreadsheets/d/' + VACATURE_RADAR.radarId
        });
      }
    }
    var result = {status: 'ok', newLeads: additions.length,
      inspected: inspected, attemptedSources: attempts, failedSources: failures,
      incomplete: attempts < sourceSpecs.length, at: now};
    PropertiesService.getScriptProperties().setProperty('VACATURE_RADAR_LAST_RUN', JSON.stringify(result));
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
  return {status: 'paused', dataPreserved: true};
}
