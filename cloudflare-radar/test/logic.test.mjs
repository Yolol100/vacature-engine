import test from 'node:test';
import assert from 'node:assert/strict';
import {
  PILOT_SOURCES,adapterUrl,buildRegisterIndex,canonicalUrl,chooseSource,cooldownMinutes,
  isValidJob,matchRegister,normalizeJobs,preliminaryInterest,runStatsRow,
  sourceActive,strongRoleKeys,toRadarRow
} from '../src/logic.mjs';

test('canonical URL strips tracking, preserves job identity, ignores generic careers links',()=>{
  assert.equal(canonicalUrl('https://jobs.lever.co/kinsta/abc?utm_source=x&job_id=99#apply'),
    'https://jobs.lever.co/kinsta/abc?job_id=99');
  assert.equal(canonicalUrl('http://jobs.lever.co/kinsta/abc'),'');
  assert.deepEqual(strongRoleKeys('https://company.example.com/careers'),[]);
  assert.ok(strongRoleKeys('https://jobs.lever.co/kinsta/abc?utm_campaign=hi').includes('ats:lever:kinsta:abc'));
  assert.ok(strongRoleKeys('https://jobs.lever.co/kinsta/abc/apply').includes('ats:lever:kinsta:abc'));
  assert.ok(strongRoleKeys('https://job-boards.greenhouse.io/foo/jobs/123').includes('ats:greenhouse:foo:123'));
  assert.ok(strongRoleKeys('https://jobs.ashbyhq.com/zapier/role').includes('ats:ashby:zapier:role'));
});
test('require both registry source and employer active',()=>{
  const rows=[['source_id'],['lever',...Array(11).fill(''),'active'],['company-kinsta',...Array(11).fill(''),'active']];
  assert.equal(sourceActive(rows,PILOT_SOURCES[1]),true);
  rows[2][12]='blocked';
  assert.equal(sourceActive(rows,PILOT_SOURCES[1]),false);
  assert.equal(chooseSource(PILOT_SOURCES,0),PILOT_SOURCES[0]);
  assert.equal(chooseSource(PILOT_SOURCES,4),PILOT_SOURCES[1]);
});
test('use real spreadsheet header layouts and later submission events',()=>{
  const vacancies=[
    ['vacancy_id','status','','','','','canonical_url','official_url'],
    ['vseen','shown','','','','','https://jobs.lever.co/kinsta/seen',''],
    ['vlate','seen','','','','','https://jobs.lever.co/kinsta/late',''],
    ['vgeneric','shown','','','','','https://company.example.com/careers',''],
    ['test:vfake','submitted','','','','','https://jobs.lever.co/kinsta/fake','']
  ];
  const apps=[
    ['vacancy_id','prepared_at','status','application_route','application_url'],
    ['vready','','prepared','','https://jobs.lever.co/kinsta/ready'],
    ['vsubmitted','','submitted','','https://jobs.lever.co/kinsta/applied'],
    ['vlate','','prepared','','https://jobs.lever.co/kinsta/late']
  ];
  const events=[
    ['event_id','vacancy_id','occurred_at','event_type','source','status_after'],
    ['e1','vlate','','submitted','','submitted']
  ];
  const i=buildRegisterIndex(vacancies,apps,events);
  assert.equal(i.known.has('ats:lever:kinsta:seen'),true);
  assert.equal(i.known.has('ats:lever:kinsta:applied'),true);
  assert.equal(i.applied.has('ats:lever:kinsta:late'),true);
  assert.equal(i.applied.has('ats:lever:kinsta:ready'),false);
  assert.equal(i.known.has('ats:lever:kinsta:fake'),false);
  assert.equal(i.known.has('url:https://company.example.com/careers'),false);
  assert.deepEqual(matchRegister({url:'https://jobs.lever.co/kinsta/late/apply',source_url:'',source_id:'lever',source_job_id:'late',identity:'lever:kinsta:late'},i),{applied:true,known:true});
});
test('normalize sources conservatively and never invent publication time',()=>{
  const sample=normalizeJobs(PILOT_SOURCES[1],[{id:'2',text:'WordPress Developer',hostedUrl:'https://jobs.lever.co/kinsta/2',categories:{location:'Remote'},createdAt:123}])[0];
  assert.equal(sample.confirmed_published_at,'');
  assert.equal(toRadarRow(sample,'2026-10-15T00:00:00Z','run1')[10],'');
  assert.equal(toRadarRow(sample,'2026-10-15T00:00:00Z','run1')[16],'niet_beoordeeld');
  assert.equal(preliminaryInterest(sample),true);
  assert.equal(isValidJob(sample),true);
  assert.equal(preliminaryInterest({...sample,title:'Human Resources Specialist'}),false);
  const ashby=normalizeJobs(PILOT_SOURCES[2],{jobs:[
    {title:'WordPress',jobUrl:'https://jobs.ashbyhq.com/zapier/123',isListed:true},
    {title:'Hidden',jobUrl:'https://jobs.ashbyhq.com/zapier/hidden',isListed:false}
  ]});
  assert.equal(ashby.length,1);
  assert.match(adapterUrl(PILOT_SOURCES[2]),/^https:\/\/api\.ashbyhq\.com\//);
  const invalid=normalizeJobs(PILOT_SOURCES[0],{jobs:[{id:5,title:'Developer',absolute_url:'https://fake.example/job/123'}]})[0];
  assert.equal(isValidJob(invalid),false);
});
test('failures and rate limits receive deterministic backoff',()=>{
  assert.equal(cooldownMinutes(1,429,undefined),15);
  assert.equal(cooldownMinutes(1,503,undefined),3);
  assert.equal(cooldownMinutes(2,503,undefined),6);
  assert.equal(cooldownMinutes(1,429,1800),30);
  assert.equal(cooldownMinutes(1,429,172800),2880,'honor 48-hour Retry-After from source');
});
test('runs metrics align to all 12 column headers, including corrected counters',()=>{
  const row=runStatsRow('rid','a','b',{sources:1,observations:21,delivered:2,known:3,applied:4,skipped:5,errors:['bad']});
  assert.deepEqual(row,['rid','a','b',1,21,2,3,4,5,1,'partial','bad']);
});
