'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const code = fs.readFileSync(path.join(__dirname, 'Code.gs'), 'utf8');
function load(extras = {}) {
  const sandbox = vm.createContext({console: {warn() {}, info() {}}, ...extras});
  vm.runInContext(code, sandbox, {filename: 'Code.gs', timeout: 2000});
  return sandbox;
}


test('30-minute trigger migration is idempotent and preserves the old trigger until replacement', () => {
  const events = [], data = new Map(), existing = {getHandlerFunction() {return 'runVacatureRadar';}};
  let triggers = [existing];
  const s = load({ScriptApp:{
    getProjectTriggers() {return triggers;},
    newTrigger(name) {
      assert.equal(name, 'runVacatureRadar');
      return {timeBased() {return this;},everyMinutes(n) {
        events.push('create:' + n); assert.equal(n, 30); return this;
      },create() {
        const trigger = {getHandlerFunction() {return 'runVacatureRadar';}};
        triggers.push(trigger); return trigger;
      }};
    },
    deleteTrigger(trigger) {events.push('delete'); triggers = triggers.filter(x => x !== trigger);}
  }});
  const props={getProperty(k) {return data.get(k)||null;},setProperty(k,v){data.set(k,v);}};
  assert.equal(s.radarEnsure30MinuteTrigger_(props),'30m_trigger_migrated');
  assert.equal(triggers.length,1);
  assert.equal(events[0],'create:30');
  assert.equal(events[1],'delete');
  assert.equal(s.radarEnsure30MinuteTrigger_(props),'30m_already_configured');
  assert.equal(events.length,2);
});

test('ambiguous triggers block migration without deleting or creating any trigger', () => {
  let creates = 0;
  const s=load({ScriptApp:{
    getProjectTriggers() {return [{getHandlerFunction(){return 'runVacatureRadar';}},
      {getHandlerFunction(){return 'runVacatureRadar';}}];},
    newTrigger() {creates++; throw Error('unexpected create');}
  }});
  const props={getProperty(){return null;}};
  assert.throws(()=>s.radarEnsure30MinuteTrigger_(props),/Multiple Radar triggers/);
  assert.equal(creates,0);
});

test('registered source URLs reject private and non-HTTPS targets', () => {
  const s=load();
  assert.equal(s.radarPublicRequestUrl_({id:'source',url:'http://example.com/jobs'},0),'');
  assert.equal(s.radarPublicRequestUrl_({id:'source',url:'https://127.0.0.1/admin'},0),'');
  assert.equal(s.radarPublicRequestUrl_({id:'source',url:'https://example.com/jobs'},0),'https://example.com/jobs');
  assert.match(s.radarPublicRequestUrl_({id:'google-jobs',url:'https://www.google.com/search'},1),
    /^https:\/\/www\.google\.com\/search\?q=.*Elementor/);
});

test('HTML JobPosting is saved only as an unverified remote role', () => {
  const s=load();
  const src={id:'company-demo',name:'Demo Employer',type:'employer_direct',url:'https://demo.example/jobs/'};
  const html='<script type="application/ld+json">'+JSON.stringify({
    '@context':'https://schema.org','@type':'JobPosting',title:'WordPress Developer',
    datePosted:'2026-11-21',jobLocationType:'TELECOMMUTE',
    applicantLocationRequirements:{name:'Europe'},
    hiringOrganization:{name:'Demo Employer'},
    description:'Build WooCommerce websites',url:'https://demo.example/jobs/123'
  })+'</script>';
  const jobs=s.radarPublicJobPostings_(html,src,src.url);
  assert.equal(jobs.length,1);
  assert.equal(jobs[0].location,'Remote - Europe');
  assert.equal(jobs[0].url,'https://demo.example/jobs/123');
  const pending=s.radarReview_(jobs[0],{max_posting_age_days:7},Date.parse('2026-11-21T12:00:00Z'));
  assert.equal(pending.status,'needs_official_review');
  const hybrid=s.radarPublicJobPostings_(html.replace('TELECOMMUTE','HYBRID'),src,src.url);
  assert.equal(hybrid.length,0);
});

test('plain careers overview cannot manufacture remote vacancy candidates', () => {
  const s=load();
  const src={id:'company-demo',name:'Demo Employer',type:'employer_direct',url:'https://demo.example/careers/'};
  const html='<a href="/careers">Visit careers</a><a href="/jobs/role1">WordPress Developer</a>'+
    '<a href="/jobs/role2">Remote WordPress Developer</a>';
  const jobs=s.radarPublicRemoteLinks_(html,src,src.url);
  assert.equal(jobs.length,1);
  assert.equal(jobs[0].url,'https://demo.example/jobs/role2');
  assert.equal(jobs[0].publishedHint,'');
});

test('all 233 registered sources get a distinct outcome on a mocked fast public sweep', () => {
  const s=load({UrlFetchApp:{fetchAll(items) {
    return items.map(()=>({getResponseCode(){return 200;},
      getContentText(){return '<html><title>Careers</title><p>No jobs identified</p></html>';}}));
  }}});
  const header=['source_id','source_name','source_type','base_url','status'];
  const data=[header], log=[];
  for(let i=0;i<233;i++){
    data.push(['source-'+i,'Employer '+i,'employer_direct','https://demo.example/jobs/'+i,'active']);
  }
  const registry={
    getSheetByName(n) {assert.equal(n,'Bronnen');
      return {getName(){return 'Bronnen';},getDataRange(){return {getValues(){return data;}}}};}
  };
  let rows=0;
  const radar={
    getSheetByName(n){return null;},
    insertSheet(n){assert.equal(n,'Broncontrole 30m');return {
      getLastRow(){return rows;},getMaxRows(){return 1000;},
      setFrozenRows(){},
      getRange(r,c,ncol,width){return {setValues(v){log.push({r,c,v});rows=Math.max(rows,r+v.length-1);}};}
    };}
  };
  const m=new Map();
  const props={getProperty(k){return m.get(k)||null;},setProperty(k,v){m.set(k,v);}};
  const result=s.radarSweepPublicRegistry_(registry,radar,props,Date.now(),{},{},
    ['wordpress_ecosystem'],{max_posting_age_days:7});
  assert.equal(result.total,233);
  assert.equal(result.attempted,233);
  assert.equal(result.pending,0);
  assert.equal(result.added.length,0);
  assert.equal(log.filter(x=>x.r===2)[0].v.length,233);
  assert.match(log[0].v[0][0],/source_id/);
});

test('30-minute Apps Script imports external worker without repeating 233 slow network requests', () => {
  const s = load();
  assert.equal(s.VACATURE_RADAR.allowedSchedule,'apps_script_30m_safe_feed_and_on_demand_deep');
  const runSource = code.slice(code.indexOf('function runVacatureRadar(event) {'),
    code.indexOf('function enableVacatureRadar() {'));
  assert.doesNotMatch(runSource,/radarSweepPublicRegistry_\(/);
  assert.match(runSource,/radarWorkerImport_\(/);
  assert.match(runSource,/worker_unavailable_or_stale/);
});


test('worker feed source inventory is checked against live Register and freshness', () => {
  const s=load();
  const now=Date.parse('2026-11-21T12:00:00Z');
  const sources=[
    {id:'company-demo',name:'Demo Corp',type:'employer_direct',url:'https://demo.example/jobs/'},
    {id:'google-jobs',name:'Google',type:'discovery',url:'https://www.google.com/search'}
  ];
  const payload={schema_version:1,generated_at:'2026-11-21T11:58:00Z',source_count:2,
    sources:sources.map(x=>({source_id:x.id,url:x.url,status:'http_200',
      checked_at:'2026-11-21T11:58:00Z',browser:'rendered',candidate_count:1,
      coverage:'rendered_public_page_only'})),observations:[],google:[{status:'http_200',browser:'rendered'}]};
  const ok=s.radarWorkerParse_(JSON.stringify(payload),sources,now);
  assert.equal(ok.registered,2);
  assert.equal(ok.attempted,2);
  assert.equal(ok.browserCount,2);
  assert.match(ok.googleStatus,/http_200/);
  assert.throws(()=>s.radarWorkerParse_(JSON.stringify({...payload,
    generated_at:'2026-11-21T01:00:00Z'}),sources,now),/stale/);
  assert.throws(()=>s.radarWorkerParse_(JSON.stringify({...payload,
    sources:[{...payload.sources[0],url:'https://evil.example/'},payload.sources[1]]}),sources,now),
    /Untrusted/);
  assert.throws(()=>s.radarWorkerParse_(JSON.stringify({...payload,source_count:233}),sources,now),
    /mismatch/);
});

test('public worker candidate intake never promotes, repeats or accepts hybrid/non-remote', () => {
  const s=load();
  const sources=[{id:'company-demo',name:'Demo Corp',
    type:'employer_direct',url:'https://demo.example/jobs/'}];
  const core={source_id:'company-demo',job_id:'job-1',employer:'Demo Corp',
    title:'WordPress Developer',url:'https://demo.example/jobs/1',
    description:'Building WooCommerce stores',location:'Remote - Netherlands',
    review_status:'unverified',published_hint:'',
    evidence:'Official JobPosting candidate'};
  const rejected=[
    {...core,url:'https://demo.example/jobs/2',location:'Hybrid - Amsterdam'},
    {...core,url:'https://demo.example/jobs/3',location:'Remote - US only'},
    {...core,url:'https://demo.example/jobs/4',title:'AI Automation Engineer'},
    {...core,url:'http://demo.example/jobs/5'},
    {...core,source_id:'not-active',url:'https://demo.example/jobs/6'},
    {...core,url:'https://demo.example/jobs/7',review_status:'verified'}
  ];
  const seen={},old={};
  const config={max_posting_age_days:7};
  const when=Date.parse('2026-11-21T12:00:00Z');
  const rows=s.radarWorkerRows_([core,...rejected],sources,seen,old,
    ['wordpress_ecosystem','web_design_development'],config,when);
  assert.equal(rows.length,1);
  assert.equal(rows[0][6],'WordPress Developer');
  assert.equal(rows[0][10],'date_unknown_review');
  assert.match(rows[0][12],/unverified|unknown/i);
  assert.equal(s.radarWorkerRows_([core],sources,seen,old,
    ['wordpress_ecosystem'],config,when).length,0);
});

test('Apps Script code parses in V8 without executing a schedule', () => {
  const ctx = load();
  assert.equal(typeof ctx.runVacatureRadar, 'function');
  assert.equal(typeof ctx.enableVacatureRadar, 'function');
  assert.equal(typeof ctx.disableVacatureRadar, 'function');
});

test('idle trigger preserves the last real scan counts and records trigger separately', () => {
  const s = load();
  const writes = {};
  const radar = {getSheetByName() {return {getRange(cell) {
    return {
      setValue(value) {writes[cell] = value;},
      getValue() {return cell === 'B29' ? 11 : '';},
      setValues(value) {writes[cell] = value;}
    };
  }};}};
  s.radarUpdateDashboard_(radar, true, {
    at: '2026-11-19T11:00:00.000Z', attemptedSources: 0,
    failedSources: 0, newLeads: 0, inspected: 0, alertCandidates: 0,
    failedAccounts: [], coolingDownSources: [], status: 'idle_no_sources_due',
    configuredSources: 20, dueSources: 0, lastSourceFetchAt: '2026-11-19T10:50:00.000Z'
  }, {});
  assert.equal(writes.B10, '2026-11-19T11:00:00.000Z');
  assert.equal(writes.B19, 'Geen bronnen aan de beurt bij deze uitvoering');
  for (const cell of ['B11','B12','B13','B14','B16','B17','B20','B22']) {
    assert.equal(Object.hasOwn(writes, cell), false, cell);
  }
  assert.equal(writes.A10, 'Laatste uitvoering (UTC)');
  assert.equal(writes.B23, 0);
  assert.equal(writes['A28:B34'][1][1], 11);
  assert.equal(writes['A28:B34'][6][1], 'Handmatig');
});


test('Workable diagnostics never assert success without an Apps Script success property', () => {
  const s = load();
  const data = new Map();
  const p = {getProperty(key) {return data.get(key) || null;}};
  const now = Date.parse('2026-11-21T10:00:00Z');
  const rows = s.radarWorkableHealth_(p, now);
  assert.equal(rows.length, 2);
  assert.match(rows[0][1], /Nog geen succesvolle/);
  assert.match(rows[1][1], /Nog geen succesvolle/);
  data.set('RADAR_SOURCE_SUCCESS_workable_awesomemotive', String(now - 5 * 60000));
  data.set('RADAR_SOURCE_OBSERVATIONS_workable_awesomemotive', '3');
  const success = s.radarWorkableHealth_(p, now);
  assert.match(success[0][1], /SUCCES/);
  assert.match(success[0][1], /ingelezen: 3/);
  assert.doesNotMatch(success[1][1], /SUCCES/);
});

test('Workable diagnostic respects retry-after and exponential cooldown', () => {
  const s = load();
  const now = Date.parse('2026-11-21T10:00:00Z');
  const data = new Map([
    ['RADAR_SOURCE_FAILURE_AT_workable_humanmade', String(now - 30 * 60000)],
    ['RADAR_SOURCE_FAILURE_COUNT_workable_humanmade', '4'],
    ['RADAR_SOURCE_RETRY_AT_workable_humanmade', String(now + 2 * 3600000)],
    ['RADAR_SOURCE_ERROR_workable_humanmade', 'Source HTTP 429']
  ]);
  const p = {getProperty(key) {return data.get(key) || null;}};
  const rows = s.radarWorkableHealth_(p, now);
  assert.match(rows[1][1], /FOUT/);
  assert.match(rows[1][1], /429/);
  assert.match(rows[1][1], /2026-11-21T12:00:00.000Z/);
  assert.equal(s.radarSourceDue_({adapter:'workable',source_id:'workable',account:'humanmade'},now,p).ready, false);
});

test('application dashboard metrics exclude test records', () => {
  const s = load();
  function sheet(rows) {return {getName() {return 'mock';}, getDataRange() {
    return {getValues() {return rows;}};
  }};}
  const register = {
    getSheetByName(name) {
      if (name === 'Applications') return sheet([
        ['vacancy_id','status'],
        ['real-ready','prepared_cv_ready'], ['real-submitted','submitted'],
        ['real-rejected','rejected'], ['test:ready','prepared_cv_ready'],
        ['real-applied','applied'], ['history:applied','applied']
      ]);
      if (name === 'ApplicationEvents') return sheet([
        ['event_id','vacancy_id','event_type'],
        ['reply-1','real-reply','employer_reply'], ['reply-1','real-reply','employer_reply'],
        ['reply-2','test:reply','employer_reply'],
        ['submitted-1','real-applied','submitted'],
        ['submitted-2','real-rejected','submitted']
      ]);
      if (name === 'Vacatures') return sheet([
        ['vacancy_id','status'], ['real-closed','closed'], ['history:closed','closed']
      ]);
      throw new Error('Unexpected sheet: ' + name);
    }
  };
  assert.deepEqual(JSON.parse(JSON.stringify(s.radarApplicationMetrics_(register))), {
    readyPackages: 1, submitted: 3, replies: 1, interviews: 0, closedOrRejected: 1, closedVacancies: 1
  });
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


test('Workable uses the official public careers API endpoint', () => {
  const s = load();
  assert.equal(
    s.radarSpecUrl_({adapter:'workable',account:'humanmade'}),
    'https://apply.workable.com/api/v1/widget/accounts/humanmade?details=true'
  );
  assert.equal(
    s.radarSpecUrl_({adapter:'workable',account:'awesomemotive'}),
    'https://apply.workable.com/api/v1/widget/accounts/awesomemotive?details=true'
  );
});

test('all official ATS endpoints disallow redirects', () => {
  const options = [];
  const s = load({UrlFetchApp:{fetch(url, opts) {
    options.push({url, opts});
    return {
      getResponseCode() {return 200;},
      getContentText() {return JSON.stringify({jobs:[]});}
    };
  }}});
  s.radarFetchSource_({adapter:'workable',account:'humanmade'});
  s.radarFetchSource_({adapter:'greenhouse',account:'acme'});
  assert.equal(options[0].url,
    'https://apply.workable.com/api/v1/widget/accounts/humanmade?details=true');
  assert.equal(options[0].opts.followRedirects, false);
  assert.equal(options[1].opts.followRedirects, false);
});

test('Greenhouse accepts a bounded large board and falls back to official summary only above cap', () => {
  const reqs = [];
  const ctx = load({
    UrlFetchApp: {
      fetch(url) {
        reqs.push(url);
        return {
          getResponseCode() {return 200;},
          getContentText() {
            return url.includes('content=false') ? JSON.stringify({jobs: []}) : 'x'.repeat(4250001);
          }
        };
      }
    }
  });
  assert.equal(ctx.radarFetchSource_({adapter:'greenhouse',account:'gitlab'}), '{"jobs":[]}');
  assert.equal(reqs.length, 2);
  assert.match(reqs[0], /content=true$/);
  assert.match(reqs[1], /content=false$/);
  assert.throws(() => ctx.radarHttp_('https://boards-api.greenhouse.io/test'), /safety budget/);
  const normal = load({UrlFetchApp:{fetch() {return {
    getResponseCode() {return 200;},
    getContentText() {return 'x'.repeat(3900000);}
  };}}});
  assert.equal(normal.radarHttp_('https://boards-api.greenhouse.io/test').length, 3900000);
});


test('Unix-second and Unix-millisecond publication dates are classified correctly', () => {
  const s=load();
  const now=Date.parse('2026-11-17T00:00:00Z');
  const d=Date.parse('2026-11-15T00:00:00Z');
  assert.equal(s.radarPublicationMs_(String(Math.trunc(d / 1000))), d);
  assert.equal(s.radarPublicationMs_(String(d)), d);
  assert.equal(s.radarPublicationMs_('2026-11-15T00:00:00Z'), d);
  assert.ok(Number.isNaN(s.radarPublicationMs_('')));
  assert.ok(Number.isNaN(s.radarPublicationMs_('abc')));
  const base={publishedHint:String(Math.trunc(d / 1000)),
    title:'WordPress Developer', location:'Remote - Netherlands',
    description:'Build WordPress plugins'};
  const result=s.radarReview_(base, {max_posting_age_days:'7'}, now);
  assert.equal(result.status,'needs_official_review');
  assert.equal(s.radarReview_({...base,publishedHint:'1792675549'},
       {max_posting_age_days:'7'},now).status,'historical_review');
});

test('Only material WordPress and website roles pass the current role-family policy', () => {
  const s = load();
  assert.equal(s.radarRelevant_('Senior Systems Engineer', 'We host WordPress websites', ['wordpress_ecosystem']), false);
  assert.equal(s.radarRelevant_('Sales Engineer', 'Help customers with WordPress hosting', ['wordpress_ecosystem']), false);
  assert.equal(s.radarRelevant_('Senior Product Designer', 'WordPress can be used by clients', ['wordpress_ecosystem']), false);
  assert.equal(s.radarRelevant_('Web Developer', 'Build custom WordPress themes', ['wordpress_ecosystem']), true);
  assert.equal(s.radarRelevant_('PHP Engineer', 'Build WooCommerce plugins', ['wordpress_ecosystem']), true);
  assert.equal(s.radarRelevant_('AI Automation Engineer', 'Build n8n automation and market WordPress products', ['wordpress_ecosystem']), false);
});

test('Past date, unknown date, US-only, hybrid and remote-Europe are distinct review outcomes', () => {
  const s=load();
  const now=Date.parse('2026-11-17T00:00:00Z');
  const config={max_posting_age_days: '7'};
  const base={title:'WordPress Developer', publishedHint:'2026-11-15T10:00:00Z',
    description:'Build WordPress plugins for remote teams',location:'Remote - Europe'};
  const check=(x)=>s.radarReview_({...base,...x},config,now);
  assert.equal(check({}).status,'needs_official_review');
  assert.equal(check({publishedHint:'2026-08-17T00:00:00Z'}).status,'historical_review');
  assert.equal(check({publishedHint:''}).status,'date_unknown_review');
  assert.equal(check({location:'Hybrid - Amsterdam'}).status,'not_fully_remote_review');
  assert.equal(check({location:'Remote - US only',description:'US only applicants'}).status,'geography_restricted_review');
  assert.equal(check({location:'Remote',description:'Build WordPress plugins'}).status,'remote_nl_unknown_review');
  assert.equal(check({location:'Remote - Worldwide'}).alert,true);
  assert.equal(check({publishedHint:'2026-11-19T00:00:00Z'}).status,'date_conflict_review');
  assert.equal(check({location:'Remote - Spain', description:'We serve customers across Europe and build WordPress plugins'}).status, 'remote_nl_unknown_review');
  assert.equal(check({location:'Remote - Netherlands', description:'Build WordPress plugins'}).alert, true);
  assert.equal(check({location:'Remote',description:'You can be based anywhere in Europe'}).alert, true);
  assert.equal(check({location:'Remote',description:'Work from anywhere in Europe'}).alert, true);
  assert.equal(check({location:'Remote',description:'We work with customers in Europe'}).status,'remote_nl_unknown_review');
});

function dataSheet(name, rows) {
  return {
    getName() {return name;},
    getDataRange() {return {getValues() {return rows.map(row => row.slice());}};},
    getLastRow() {return rows.length;},
    getMaxRows() {return 1500;},
    insertRowsAfter() {throw new Error('Unexpected sheet enlargement');},
    getRange(a, b, c, d) {
      if (typeof a === 'string') {
        const cell = a.match(/^([AB])(\d+)/);
        b = cell[1] === 'A' ? 1 : 2;
        a = Number(cell[2]);
      }
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
function mockRun(schedule, jobOverrides = {}) {
  const cols = ['candidate_key','first_seen_utc','last_seen_utc','source_id',
    'source_job_id','employer','title','official_or_board_url','published_hint',
    'location','review_status','source_type','review_note'];
  const register = {
    Config: dataSheet('Config', [['key','value'], ['ingestion_schedule', schedule],
      ['target_role_families', 'wordpress_ecosystem'], ['allowed_work_locations', 'NL'], ['remote_scope','worldwide'], ['allowed_listing_languages','nl,en']]),
    Bronnen: dataSheet('Bronnen', [['source_id','status'], ['greenhouse','active']]),
    Vacatures: dataSheet('Vacatures', [['canonical_url','official_url']]),
    Applications: dataSheet('Applications', [['vacancy_id','application_url','status']]),
    ApplicationEvents: dataSheet('ApplicationEvents', [['event_id','vacancy_id','event_type']]),
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
      setProperty(k, v) {props.set(k, String(v));},
      deleteProperty(k) {props.delete(k);}
    };}},
    UrlFetchApp: {fetch(url) {
      fetches.push(url);
      let raw;
      if (url.includes('source-specs.deploy.json')) {
        raw = JSON.stringify([{source_id:'greenhouse',source_type:'ats',adapter:'greenhouse',account:'acme',employer:'Acme',listing_language:'en'}]);
      } else if (url.startsWith('https://boards-api.greenhouse.io/')) {
        const base = {id:1,title:'WordPress Developer',
          absolute_url:'https://boards.greenhouse.io/acme/jobs/1?utm_source=radar',
          first_published:'2026-11-15T00:00:00Z'};
        const overrides = Array.isArray(jobOverrides) ? jobOverrides : [jobOverrides];
        raw = JSON.stringify({jobs:overrides.map(extra => ({...base, ...extra}))});
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


test('source failures have bounded exponential retry delay and success does not use the cooldown', () => {
  const s=load();
  const source={adapter:'greenhouse',source_id:'greenhouse',account:'acme'};
  const now=Date.parse('2026-11-17T00:00:00Z');
  const state=new Map();
  const props={getProperty(k) {return state.get(k) || null;}};
  assert.equal(s.radarSourceDue_(source,now,props).ready,true);
  const info=s.radarSourceDue_(source,now,props);
  state.set(info.failAtKey,String(now));
  state.set(info.failCountKey,'3'); // 60-minute cooldown
  assert.equal(s.radarSourceDue_(source,now+15*60000,props).ready,false);
  assert.equal(s.radarSourceDue_(source,now+15*60000,props).coolingDown,true);
  assert.equal(s.radarSourceDue_(source,now+59*60000,props).ready,false);
  assert.equal(s.radarSourceDue_(source,now+60*60000,props).ready,true);
  state.set(info.failAtKey,'0');
  state.set(info.failCountKey,'0');
  assert.equal(s.radarSourceDue_(source,now+60*60000,props).ready,true);
  state.set(info.key,String(now+60*60000));
  assert.equal(s.radarSourceDue_(source,now+65*60000,props).ready,false);
  assert.equal(s.radarSourceDue_(source,now+75*60000,props).ready,true);
});

test('a cooling-down source remains degraded while another source is due', () => {
  const s=load();
  assert.equal(s.radarRunStatus_(1,0,1),'degraded_source_cooldown');
  assert.equal(s.radarRunStatus_(0,0,0),'idle_no_sources_due');
  assert.equal(s.radarRunStatus_(1,0,0),'ok');
  assert.equal(s.radarRunStatus_(0,1,0),'degraded_source_failures');
});


test('missing original date and secondary salary data keep remote WordPress lead pending', () => {
  const m = mockRun('apps_script_15m_fastlane_and_on_demand_deep', {
    first_published: '',
    location: {name: 'Remote - Netherlands'},
    content: '<p>Build WordPress and WooCommerce websites.</p>'
    // The employer ATS does not provide salary information.
  });
  const result = m.s.runVacatureRadar();
  assert.equal(result.attemptedSources, 1);
  assert.equal(result.failedSources, 0);
  assert.equal(result.newLeads, 1);
  const row = m.radar['Bronvondsten'].getDataRange().getValues()[1];
  assert.equal(row[6], 'WordPress Developer');
  assert.equal(row[8], '');
  assert.equal(row[9], 'Remote - Netherlands');
  assert.equal(row[10], 'date_unknown_review');
  assert.match(row[12], /Original posting date unverified/);
  assert.equal(m.register.Vacatures.getLastRow(), 1);
  assert.equal(m.register.Applications.getLastRow(), 1);
  assert.equal(m.mails.length, 0);
});

test('a source cooling down after repeated errors remains visibly degraded', () => {
  const m=mockRun('apps_script_15m_fastlane_and_on_demand_deep');
  const now=Date.now();
  m.props.set('RADAR_SOURCE_FAILURE_AT_greenhouse_acme',String(now));
  m.props.set('RADAR_SOURCE_FAILURE_COUNT_greenhouse_acme','3');
  const result=m.s.runVacatureRadar();
  assert.equal(result.status,'degraded_source_cooldown');
  assert.equal(result.coolingDownSources[0],'greenhouse/acme');
  assert.equal(result.attemptedSources,0);
  assert.equal(result.failedSources,0);
  assert.equal(m.fetches.filter(x=>x.includes('greenhouse.io')).length,0);
});

test('an idle scheduled run is reported as no sources due, not a fresh successful poll', () => {
  const m=mockRun('apps_script_15m_fastlane_and_on_demand_deep');
  m.props.set('RADAR_SOURCE_SUCCESS_greenhouse_acme',String(Date.now()));
  const result=m.s.runVacatureRadar();
  assert.equal(result.status,'idle_no_sources_due');
  assert.equal(result.configuredSources,1);
  assert.equal(result.dueSources,0);
  assert.equal(result.attemptedSources,0);
  assert.equal(result.failedSources,0);
  assert.equal(result.lastSourceFetchAt,'');
  assert.equal(m.radar['Bronvondsten'].getLastRow(),1);
  assert.equal(m.mails.length,0);
  // GitHub spec manifest is retrieved once, but the source API is not polled.
  assert.equal(m.fetches.filter(x=>x.includes('greenhouse.io')).length,0);
});
test('enabled discovery appends only a new, unverified lead and dedupes on re-run', () => {
  const m = mockRun('apps_script_15m_fastlane_and_on_demand_deep');
  const one = m.s.runVacatureRadar();
  assert.equal(one.newLeads, 1);
  assert.equal(one.attemptedSources, 1);
  assert.equal(m.radar['Bronvondsten'].getLastRow(), 2);
  assert.equal(m.radar['Bronvondsten'].getDataRange().getValues()[1][10], 'remote_nl_unknown_review');
  assert.equal(m.register.Vacatures.getLastRow(), 1);
  assert.equal(m.register.Applications.getLastRow(), 1);
  // Force the same provider to be fetched again, proving cross-run URL dedupe.
  m.props.set('RADAR_SOURCE_SUCCESS_greenhouse_acme', '0');
  const two = m.s.runVacatureRadar({triggerUid: 'schedule'});
  assert.equal(two.triggered, true);
  assert.equal(two.lastTriggerAt, two.at);
  assert.equal(two.lastSourceSuccessAt, two.at);
  assert.equal(two.attemptedSources, 1);
  assert.equal(two.newLeads, 0);
  assert.equal(m.radar['Bronvondsten'].getLastRow(), 2);
  assert.equal(m.mails.length, 0);
  assert.equal(m.props.get('VACATURE_RADAR_LAST_RUN') !== undefined, true);
});

test('rate-limit responses keep the provider Retry-After delay', () => {
  const s = load({UrlFetchApp: {fetch() {
    return {getResponseCode() {return 429;}, getAllHeaders() {return {'Retry-After': '1800'};}};
  }}});
  const now = Date.now();
  assert.throws(() => s.radarFetchSource_({adapter:'workable', account:'humanmade'}), error =>
    /429/.test(error.message) && error.retryAt >= now + 1800000);
  assert.equal(s.radarRetryAfterMs_({'retry-after': 'Thu, 19 Nov 2026 11:00:00 GMT'},
    Date.parse('2026-11-19T10:00:00Z')), Date.parse('2026-11-19T11:00:00Z'));
  const state = new Map();
  const props = {getProperty(k) {return state.get(k) || null;}};
  const spec = {adapter:'workable', source_id:'workable', account:'humanmade'};
  const keys = s.radarSourceDue_(spec, now, props);
  state.set(keys.retryAtKey, String(now + 1800000));
  assert.equal(s.radarSourceDue_(spec, now + 900000, props).ready, false);
  assert.equal(s.radarSourceDue_(spec, now + 1800000, props).ready, true);
});

test('Himalayas missing geography does not imply worldwide eligibility', () => {
  const s = load();
  const rows = s.radarCandidates_({adapter:'himalayas', source_id:'himalayas', account:'global'},
    JSON.stringify({jobs:[{guid:'x', title:'WordPress Developer', pubDate:1795000000,
      description:'Remote work with CET hours on a contractor contract.',
      applicationLink:'https://himalayas.app/jobs/wp-dev'}]}));
  assert.equal(rows[0].location, '');
  assert.equal(s.radarPublicationMs_(rows[0].publishedHint), 1795000000000);
  assert.equal(s.radarReview_(rows[0], {max_posting_age_days:7}, 1795000000000).alert, false);
});

test('Workable public job locations never turn Remote Spain into remote Netherlands', () => {
  const s = load();
  const rows = s.radarCandidates_({adapter:'workable', source_id:'workable', account:'acme'},
    JSON.stringify({jobs:[{shortcode:'x', title:'WordPress Developer', published_on:'2026-11-18',
      telecommuting:true, locations:[{country:'Spain'}],
      url:'https://apply.workable.com/j/x'}]}));
  assert.equal(rows[0].location, 'Remote - Spain');
  assert.equal(s.radarReview_(rows[0], {max_posting_age_days:7}, Date.parse('2026-11-19')).alert, false);
});

test('a new recent remote NL lead uses the radar alert and is not emailed again', () => {
  const m = mockRun('apps_script_15m_fastlane_and_on_demand_deep', {
    first_published: new Date().toISOString(), location: {name:'Remote - Netherlands'}
  });
  m.props.set('VACATURE_RADAR_ALERT_EMAIL', 'radar@example.com');
  const first = m.s.runVacatureRadar();
  assert.equal(first.alertCandidates, 1);
  assert.equal(m.mails.length, 1);
  assert.equal(m.mails[0].to, 'radar@example.com');
  assert.match(m.mails[0].body, /NIET geverifieerd/);
  m.props.set('RADAR_SOURCE_SUCCESS_greenhouse_acme', '0');
  assert.equal(m.s.runVacatureRadar().alertCandidates, 0);
  assert.equal(m.mails.length, 1);
});

test('Servebolt RSS is pinned to its official employer source', () => {
  const s = load();
  const spec = {source_id:'teamtailor', source_type:'ats', adapter:'teamtailor', account:'servebolt',
    employer:'Servebolt', endpoint:'https://careers.servebolt.com/jobs.rss',
    options:{registry_source_id:'company-servebolt'}};
  assert.equal(s.radarSpecUrl_(spec), spec.endpoint);
  assert.equal(s.radarSpecUrl_({...spec, endpoint:'https://elsewhere.example/jobs.rss'}), '');
  assert.equal(s.radarSpecUrl_({...spec, options:{registry_source_id:'company-other'}}), '');
  assert.equal(s.radarSpecUrl_({...spec, employer:'Other'}), '');
  assert.equal(s.radarSpecUrl_({...spec, employer:''}), '');
  assert.throws(() => s.radarCandidates_(spec, '<!DOCTYPE rss><rss/>'), /declaration/);
});

test('Servebolt RSS keeps the official job ID and never guesses a remote country', () => {
  const item = fields => ({getChild(name) {
    return Object.hasOwn(fields, name) ? {getText() {return fields[name];}} : null;
  }});
  const rows = [
    item({title:'WordPress Developer', link:'https://careers.servebolt.com/jobs/123-wordpress-developer',
          remoteStatus:'fully', pubDate:'Wed, 18 Nov 2026 16:02:43 +0100'}),
    item({title:'WordPress Developer', link:'https://careers.servebolt.com/jobs/124-wordpress-developer',
          remoteStatus:'hybrid'}),
    item({title:'WordPress Developer', link:'https://careers.servebolt.com/jobs/125-wordpress-developer',
          remoteStatus:'onsite'}),
    item({title:'WordPress Developer', link:'https://careers.servebolt.com/jobs/126-wordpress-developer',
          remoteStatus:'on-site'}),
    item({title:'WordPress Developer', link:'https://careers.servebolt.com/jobs/127-wordpress-developer',
          remoteStatus:'on site'}),
    item({title:'WordPress Developer', link:'https://elsewhere.example/jobs/128-wordpress-developer'}),
  ];
  const s = load({XmlService:{parse() {return {getRootElement() {
    return {getChild(name) {return name === 'channel' ? {getChildren() {return rows;}} : null;}};
  }};}}});
  const spec = {source_id:'teamtailor', source_type:'ats', adapter:'teamtailor', account:'servebolt',
    employer:'Servebolt'};
  const result = s.radarCandidates_(spec, '<rss/>');
  assert.equal(result.length, 1);
  assert.equal(result[0].jobId, 'servebolt:123');
  assert.equal(result[0].location, 'Remote');
  assert.equal(s.radarReview_(result[0], {max_posting_age_days:7}, Date.parse('2026-11-19')).alert, false);
});

test('shared generic careers listings keep separate employer roles while blocking duplicates', () => {
  const s = load();
  const cases = [
    ['https://example.org/careers', true],
    ['https://example.org/jobs/', true],
    ['https://example.org/about/careers', true],
    ['https://example.org/jobs/wordpress-developer', false],
    ['https://example.org/careers/support-engineer', false]
  ];
  for (const [url, expected] of cases) assert.equal(s.radarSharedCareersUrl_(url), expected);
  assert.notEqual(s.radarIdentity_('Themeco', 'Frontend Developer'),
                  s.radarIdentity_('Themeco', 'Technical Support Advisor'));
  assert.equal(s.radarIdentity_(' THEMeco ', ' Frontend DEVELOPER '),
               s.radarIdentity_('Themeco', 'Frontend Developer'));
  function sheet(rows) {return {getName(){return 'mock';},getDataRange(){return {getValues(){return rows;}};}};}
  const register = {getSheetByName(name) {
    if (name === 'Vacatures') return sheet([
      ['employer','title','canonical_url','official_url'],
      ['Themeco','Frontend Developer','https://themeco.com/careers','https://themeco.com/careers'],
      ['MemberPress','Customer Success Agent','https://memberpress.com/careers/support-engineer','https://memberpress.com/careers/support-engineer']
    ]);
    if (name === 'Applications') return sheet([['application_url'],['https://themeco.com/careers']]);
    if (name === 'JobSnapshots') return sheet([['canonical_url']]);
    throw new Error(name);
  }};
  const radar = {getSheetByName(name) {
    if (name === 'Nieuwe vacatures') return sheet([['officiele_url']]);
    if (name === 'Bronvondsten') return sheet([['employer','title'],['Themeco','Frontend Developer']]);
    throw new Error(name);
  }};
  const urls = s.radarKnownUrls_(register, radar);
  assert.equal(Boolean(urls['https://themeco.com/careers']), false);
  assert.equal(Boolean(urls['https://memberpress.com/careers/support-engineer']), true);
  const spec = {adapter:'generic',source_id:'themeco'};
  const career = 'https://themeco.com/careers?page=2';
  const a = s.radarObservationKey_(spec,{sourceId:'themeco',jobId:career,url:career,employer:'Themeco',title:'Frontend Developer'});
  const b = s.radarObservationKey_(spec,{sourceId:'themeco',jobId:career,url:career,employer:'Themeco',title:'Technical Support Advisor'});
  assert.notEqual(a,b);
  assert.equal(a,s.radarObservationKey_(spec,{sourceId:'themeco',jobId:career,url:career,employer:' THEMeco ',title:'frontend developer'}));
  assert.notEqual(
    s.radarObservationKey_({adapter:'lever'}, {sourceId:'lever',jobId:'1234',url:'https://jobs.lever.co/themeco',employer:'Themeco',title:'Web Developer'}),
    s.radarObservationKey_({adapter:'lever'}, {sourceId:'lever',jobId:'9876',url:'https://jobs.lever.co/themeco',employer:'Themeco',title:'Web Developer'})
  );
  assert.equal(s.radarSharedCareersUrl_('https://jobs.lever.co/themeco'),true);
  assert.equal(s.radarSharedCareersUrl_('https://boards.greenhouse.io/themeco'),true);
  assert.equal(s.radarSharedCareersUrl_('https://jobs.lever.co/themeco/1234'),false);
  assert.equal(s.radarSharedCareersUrl_('https://example.org/vacatures/page/10'),true);
});


test('global discovery retains NL-only execution and rejects management/W2-only leads', () => {
  const s = load();
  assert.equal(s.radarRelevant_('Senior WordPress Developer','',['wordpress_ecosystem','web_design_development']), true);
  assert.equal(s.radarRelevant_('Engineering Manager - APAC','Build websites',['wordpress_ecosystem','web_design_development']), false);
  assert.equal(s.radarRelevant_('WordPress Technical Lead','Build themes',['wordpress_ecosystem']), false);
  const now=Date.parse('2026-11-20T12:00:00Z'), base={publishedHint:'2026-11-19T12:00:00Z',description:'100% remote role',location:'Remote'};
  const us = s.radarReview_({...base,description:'W2 only. Must be based in the United States.'},{max_posting_age_days:'7'},now);
  assert.equal(us.status,'geography_restricted_review');
  assert.equal(us.alert,false);
  const europe = s.radarReview_({...base,location:'Remote Europe'}, {max_posting_age_days:'7'},now);
  assert.equal(europe.status,'needs_official_review');
  const asia = s.radarReview_({...base,location:'Remote Japan'}, {max_posting_age_days:'7'},now);
  assert.equal(asia.alert,false);
});


test('two role IDs on one generic careers URL are stored separately and deduped on replay', () => {
  const listing='https://jobs.lever.co/acme?page=2';
  const m=mockRun('apps_script_15m_fastlane_and_on_demand_deep',[
    {id:711,title:'WordPress Developer',absolute_url:listing},
    {id:712,title:'WooCommerce Developer',absolute_url:listing}
  ]);
  const first=m.s.runVacatureRadar({triggerUid:'test'});
  assert.equal(first.newLeads,2);
  const items=m.radar.Bronvondsten.getDataRange().getValues().slice(1);
  assert.equal(items.length,2);
  assert.notEqual(items[0][0],items[1][0]);
  for(const k of [...m.props.keys()]) {
    if(k.startsWith('RADAR_SOURCE_SUCCESS_')) m.props.delete(k);
  }
  const second=m.s.runVacatureRadar({triggerUid:'test'});
  assert.equal(second.newLeads,0);
  assert.equal(m.radar.Bronvondsten.getLastRow(),3);
});


test('one-time Workable migration clears only stale old-URL cooldown and preserves future backoff', () => {
  const s = load();
  const values = new Map([
    ['RADAR_SOURCE_FAILURE_AT_workable_awesomemotive','1000'],
    ['RADAR_SOURCE_FAILURE_COUNT_workable_awesomemotive','4'],
    ['RADAR_SOURCE_RETRY_AT_workable_awesomemotive','9999999999999'],
    ['RADAR_SOURCE_FAILURE_AT_workable_humanmade','1000'],
    ['RADAR_SOURCE_FAILURE_COUNT_workable_humanmade','4'],
    ['RADAR_SOURCE_RETRY_AT_workable_humanmade','9999999999999'],
    ['RADAR_SOURCE_FAILURE_COUNT_greenhouse_acme','5']
  ]);
  const props={getProperty(k){return values.get(k)||null;},setProperty(k,v){values.set(k,String(v));},deleteProperty(k){values.delete(k);}};
  const specs=[{adapter:'workable',source_id:'workable',account:'awesomemotive'},
               {adapter:'workable',source_id:'workable',account:'humanmade'},
               {adapter:'greenhouse',source_id:'greenhouse',account:'acme'}];
  assert.equal(s.radarMigrateWorkableDirectEndpoint_(specs,props),true);
  assert.equal(values.has('RADAR_SOURCE_RETRY_AT_workable_awesomemotive'),false);
  assert.equal(values.has('RADAR_SOURCE_RETRY_AT_workable_humanmade'),false);
  assert.equal(values.get('RADAR_SOURCE_FAILURE_COUNT_greenhouse_acme'),'5');
  values.set('RADAR_SOURCE_FAILURE_COUNT_workable_humanmade','1');
  assert.equal(s.radarMigrateWorkableDirectEndpoint_(specs,props),false);
  assert.equal(values.get('RADAR_SOURCE_FAILURE_COUNT_workable_humanmade'),'1');
});
