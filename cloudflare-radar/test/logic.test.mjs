import test from 'node:test';
import assert from 'node:assert/strict';
import {PILOT_SOURCES,adapterUrl,canonicalUrl,isValidJob,normalizeJobs,registerKnown,sourceActive,toRadarRow} from '../src/logic.mjs';

test('canonical URL strips tracking but preserves job identity',()=>{
  assert.equal(canonicalUrl('https://jobs.lever.co/kinsta/123?utm_source=x&job_id=99#apply'),'https://jobs.lever.co/kinsta/123?job_id=99');
  assert.equal(canonicalUrl('http://jobs.lever.co/kinsta/123'),'');
});
test('only active canonical source and employer are allowed',()=>{
  const rows=[['source_id'],['greenhouse',...Array(11).fill(''),'active'],['company-automattic',...Array(11).fill(''),'active']];
  assert.equal(sourceActive(rows,PILOT_SOURCES[0]),true);
  rows[2][12]='blocked';
  assert.equal(sourceActive(rows,PILOT_SOURCES[0]),false);
});
test('known submitted and shown roles excluded; draft alone not excluded',()=>{
  const vacancies=[['header'],['v1','shown','','','','','https://jobs.lever.co/kinsta/known',''],['v2','ready','','','','','https://jobs.lever.co/kinsta/ready','']];
  const applications=[['header'],['v1','','submitted','','https://jobs.lever.co/kinsta/known'],['v2','','drafted','','https://jobs.lever.co/kinsta/ready'],['v3','','submitted','','https://jobs.lever.co/kinsta/submitted']];
  const known=registerKnown(vacancies,applications);
  assert.equal(known.has('https://jobs.lever.co/kinsta/known'),true);
  assert.equal(known.has('https://jobs.lever.co/kinsta/submitted'),true);
  assert.equal(known.has('https://jobs.lever.co/kinsta/ready'),false);
});
test('publication time is never inferred from created or updated fields',()=>{
  const job=normalizeJobs(PILOT_SOURCES[1],[{id:'2',text:'WordPress Developer',hostedUrl:'https://jobs.lever.co/kinsta/2',categories:{location:'Remote'},createdAt:123}])[0];
  assert.equal(job.confirmed_published_at,'');
  assert.equal(toRadarRow(job,'2026-10-15T00:00:00Z','run1')[10],'');
  assert.equal(toRadarRow(job,'2026-10-15T00:00:00Z','run1')[16],'niet_beoordeeld');
  assert.equal(isValidJob(job),true);
});
test('Ashby official postings may omit id and unlisted posts are ignored',()=>{
  const jobs=normalizeJobs(PILOT_SOURCES[2],{jobs:[{title:'WordPress',jobUrl:'https://jobs.ashbyhq.com/zapier/123',isListed:true},{title:'Hidden',jobUrl:'https://jobs.ashbyhq.com/zapier/hidden',isListed:false}]});
  assert.equal(jobs.length,1);
  assert.ok(jobs[0].source_job_id.includes('/zapier/123'));
  assert.match(adapterUrl(PILOT_SOURCES[2]),/^https:\/\/api\.ashbyhq\.com\//);
});
test('reject untrusted host even when source-shaped',()=>{
  const bad=normalizeJobs(PILOT_SOURCES[0],{jobs:[{id:5,title:'Developer',absolute_url:'https://unexpected.example/apply'}]})[0];
  assert.equal(isValidJob(bad),false);
});
