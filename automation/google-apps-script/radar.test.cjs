'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const code = fs.readFileSync(path.join(__dirname, 'Code.gs'), 'utf8');
function load(extras = {}) {
  const sandbox = vm.createContext({console: {warn() {}}, ...extras});
  vm.runInContext(code, sandbox, {filename: 'Code.gs', timeout: 2000});
  return sandbox;
}

test('Apps Script code parses in V8 without executing a schedule', () => {
  const ctx = load();
  assert.equal(typeof ctx.runVacatureRadar, 'function');
  assert.equal(typeof ctx.enableVacatureRadar, 'function');
  assert.equal(typeof ctx.disableVacatureRadar, 'function');
});

test('canonical URL removes tracking parameters, never private or HTTP hosts', () => {
  const s = load();
  assert.equal(s.radarNormalizeUrl_('https://jobs.example.com/role/1/?utm_source=a&gclid=1&ref=person#apply'),
               'https://jobs.example.com/role/1?ref=person');
  assert.equal(s.radarNormalizeUrl_('http://jobs.example.com/role/1'), '');
  assert.equal(s.radarNormalizeUrl_('https://localhost/admin'), '');
  assert.equal(s.radarNormalizeUrl_('https://192.168.1.5/admin'), '');
  assert.equal(s.radarNormalizeUrl_('https://jobs.example.com/role/1/'),
               'https://jobs.example.com/role/1');
});

test('WordPress-only policy does not accept generic frontend and AI automation jobs', () => {
  const s = load();
  assert.equal(s.radarRelevant_('WordPress Developer', '', ['wordpress_ecosystem']), true);
  assert.equal(s.radarRelevant_('PHP Engineer', 'Build WooCommerce plugins', ['wordpress_ecosystem']), true);
  assert.equal(s.radarRelevant_('React frontend developer', 'Build a mobile app', ['wordpress_ecosystem']), false);
  assert.equal(s.radarRelevant_('AI Automation Engineer', 'Implement n8n flows', ['wordpress_ecosystem']), false);
  assert.equal(s.radarRelevant_('Web Designer', '', ['web_design_development']), true);
});

test('Ashby hybrid, hidden listings and unknown status are never marked verified', () => {
  const s = load();
  const spec = {adapter: 'ashby', account: 'acme', source_id: 'ashby', source_type: 'ats'};
  const rows = [
    {id: 'hybrid', title: 'WordPress Engineer', jobUrl: 'https://jobs.ashbyhq.com/acme/hybrid',
     isListed: true, isRemote: true, workplaceType: 'Hybrid'},
    {id: 'hidden', title: 'WordPress Engineer', jobUrl: 'https://jobs.ashbyhq.com/acme/hidden',
     isListed: false, workplaceType: 'Remote'},
    {id: 'remote', title: 'WordPress Engineer', jobUrl: 'https://jobs.ashbyhq.com/acme/remote',
     isListed: true, workplaceType: 'Remote', publishedAt: '2026-11-15'},
  ];
  const result = s.radarCandidates_(spec, JSON.stringify({jobs: rows}));
  assert.equal(result.length, 1);
  assert.equal(result[0].jobId, 'acme:remote');
  assert.match(result[0].note, /original date unverified/i);
});

test('Greenhouse does not treat updated_at as the original publication', () => {
  const s = load();
  const spec = {adapter: 'greenhouse', account: 'acme', source_id: 'greenhouse', source_type: 'ats'};
  const result = s.radarCandidates_(spec, JSON.stringify({jobs: [
    {id: 1, title: 'WordPress Developer',
     absolute_url: 'https://boards.greenhouse.io/acme/jobs/1',
     updated_at: '2026-11-16'},
  ]}));
  assert.equal(result.length, 1);
  assert.equal(result[0].publishedHint, '');
});

test('Lever EU region is explicit and invalid ATS tokens are rejected', () => {
  const s = load();
  assert.match(s.radarSpecUrl_({adapter: 'lever', account: 'acme', options: {api_region: 'eu'}}),
               /^https:\/\/api\.eu\.lever\.co\/v0\/postings\/acme/);
  assert.match(s.radarSpecUrl_({adapter: 'lever', account: 'acme'}),
               /^https:\/\/api\.lever\.co\/v0\/postings\/acme/);
  assert.equal(s.radarSpecUrl_({adapter: 'lever', account: '../evil'}), '');
});

test('SmartRecruiters cannot manufacture a job URL from just a job ID', () => {
  const s = load();
  const spec = {adapter: 'smartrecruiters', account: 'acme', source_id: 'smartrecruiters', source_type: 'ats'};
  const result = s.radarCandidates_(spec, JSON.stringify({content: [
    {id: '1', name: 'WordPress Developer'},
    {id: '2', name: 'WordPress Developer', applyUrl: 'https://jobs.smartrecruiters.com/acme/2'},
  ]}));
  assert.equal(result.length, 1);
  assert.equal(result[0].url, 'https://jobs.smartrecruiters.com/acme/2');
});

test('supported non-ATS discovery feeds produce only observations', () => {
  const s = load();
  const examples = [
    ['remoteok', [{id: 7, position: 'WordPress Developer', apply_url: 'https://remoteok.com/remote-jobs/7'}]],
    ['himalayas', {jobs: [{guid: 'x', title: 'WordPress Developer',
      applicationLink: 'https://himalayas.app/jobs/wp-dev'}]}],
    ['jobicy', {jobs: [{id: 8, jobTitle: 'WordPress Developer', url: 'https://jobicy.com/jobs/8'}]}],
    ['remotive', {jobs: [{id: 9, title: 'WordPress Developer', url: 'https://remotive.com/remote-jobs/9'}]}],
  ];
  for (const [adapter, data] of examples) {
    const rows = s.radarCandidates_({adapter, source_id: adapter, source_type: 'job_board', account: 'global'},
                                   JSON.stringify(data));
    assert.equal(rows.length, 1, adapter);
    assert.ok(rows[0].url.startsWith('https://'), adapter);
  }
});

function dataSheet(name, rows) {
  return {
    getName() {return name;},
    getDataRange() {return {getValues() {return rows.map(row => row.slice());}};},
    getLastRow() {return rows.length;},
    getMaxRows() {return 1500;},
    insertRowsAfter() {throw new Error('Unexpected sheet enlargement');},
    getRange(a, b, c, d) {
      return {
        getValue() {return rows[a - 1]?.[b - 1] || '';},
        setValue(v) {
          if (typeof a === 'string') return;
          while (rows.length < a) rows.push([]);
          rows[a - 1][b - 1] = v;
        },
        setValues(values) {
          for (let i = 0; i < values.length; i++) {
            while (rows.length < a + i) rows.push([]);
            for (let j = 0; j < values[i].length; j++) rows[a + i - 1][b + j - 1] = values[i][j];
          }
        }
      };
    }
  };
}
function mockRun(schedule) {
  const cols = ['candidate_key','first_seen_utc','last_seen_utc','source_id',
    'source_job_id','employer','title','official_or_board_url','published_hint',
    'location','review_status','source_type','review_note'];
  const register = {
    Config: dataSheet('Config', [['key','value'], ['ingestion_schedule', schedule],
      ['target_role_families', 'wordpress_ecosystem']]),
    Bronnen: dataSheet('Bronnen', [['source_id','status'], ['greenhouse','active']]),
    Vacatures: dataSheet('Vacatures', [['canonical_url','official_url']]),
    Applications: dataSheet('Applications', [['application_url']]),
    JobSnapshots: dataSheet('JobSnapshots', [['canonical_url']]),
  };
  const radar = {
    'Bronvondsten': dataSheet('Bronvondsten', [cols]),
    'Nieuwe vacatures': dataSheet('Nieuwe vacatures', [['officiele_url']]),
    Dashboard: dataSheet('Dashboard', [['name','value']])
  };
  const props = new Map(); const fetches = []; const mails = [];
  const stub = {
    SpreadsheetApp: {
      openById(id) {return {
        getSheetByName(name) {return (id === '1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0' ?
          register : radar)[name] || null;}
      };},
      flush() {},
    },
    LockService: {getScriptLock() {return {tryLock() {return true;}, releaseLock() {}};}},
    PropertiesService: {getScriptProperties() {return {
      getProperty(k) {return props.get(k) || null;},
      setProperty(k, v) {props.set(k, String(v));}
    };}},
    UrlFetchApp: {fetch(url) {
      fetches.push(url);
      let raw;
      if (url.includes('source-specs.deploy.json')) {
        raw = JSON.stringify([{source_id:'greenhouse',source_type:'ats',adapter:'greenhouse',account:'acme',employer:'Acme'}]);
      } else if (url.startsWith('https://boards-api.greenhouse.io/')) {
        raw = JSON.stringify({jobs:[{
          id:1,title:'WordPress Developer',
          absolute_url:'https://boards.greenhouse.io/acme/jobs/1?utm_source=radar',
          first_published:'2026-11-15T00:00:00Z'
        }]});
      } else {
        throw new Error('Unexpected request: ' + url);
      }
      return {getResponseCode() {return 200;}, getContentText() {return raw;}};
    }},
    MailApp: {sendEmail(email) {mails.push(email);}},
    Session: {getEffectiveUser() {return {getEmail() {return '';}};}},
  };
  return {s: load(stub), register, radar, fetches, props, mails};
}

test('disabled policy makes no public requests, writes or emails', () => {
  const m = mockRun('on_demand_chatgpt_only');
  const result = m.s.runVacatureRadar();
  assert.equal(result.status, 'disabled_by_live_config');
  assert.equal(m.fetches.length, 0);
  assert.equal(m.radar['Bronvondsten'].getLastRow(), 1);
  assert.equal(m.mails.length, 0);
});

test('enabled discovery appends only a new, unverified lead and dedupes on re-run', () => {
  const m = mockRun('apps_script_15m_fastlane_and_on_demand_deep');
  const one = m.s.runVacatureRadar();
  assert.equal(one.newLeads, 1);
  assert.equal(one.attemptedSources, 1);
  assert.equal(m.radar['Bronvondsten'].getLastRow(), 2);
  assert.equal(m.radar['Bronvondsten'].getDataRange().getValues()[1][10], 'needs_official_review');
  assert.equal(m.register.Vacatures.getLastRow(), 1);
  assert.equal(m.register.Applications.getLastRow(), 1);
  // Force the same provider to be fetched again, proving cross-run URL dedupe.
  m.props.set('RADAR_SOURCE_SUCCESS_greenhouse_acme', '0');
  const two = m.s.runVacatureRadar();
  assert.equal(two.attemptedSources, 1);
  assert.equal(two.newLeads, 0);
  assert.equal(m.radar['Bronvondsten'].getLastRow(), 2);
  assert.equal(m.mails.length, 0);
  assert.equal(m.props.get('VACATURE_RADAR_LAST_RUN') !== undefined, true);
});
