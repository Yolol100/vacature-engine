import test from 'node:test';
import assert from 'node:assert/strict';
import {
  PILOT_SOURCES,canonicalUrl,strongRoleKeys,isValidJob,
  normalizeJobs,preliminaryInterest,buildRegisterIndex,matchRegister,toRadarRow
} from '../src/logic.mjs';
import {safeDiagnosticError} from '../src/health.mjs';

const sample=(source,job)=>normalizeJobs(source,source.source_id==='lever'?[job]:{jobs:[job]})[0];

test('No false negatives on directly relevant WordPress and web developer titles',()=>{
  for(const title of ['WordPress Developer','WooCommerce Engineer','Elementor Specialist','Web Developer','Senior Web Developer','PHP Developer','PHP Engineer','Full Stack Web Developer','React Frontend Engineer','n8n Automation Developer']){
    assert.equal(preliminaryInterest({title,location:'Europe',remote:'remote'}),true,'false negative: '+title);
  }
  for(const title of ['Accounts Payable Clerk','Recruiting Manager','Sales Executive','Office Administrator']){
    assert.equal(preliminaryInterest({title,location:'Netherlands',remote:'remote'}),false,'unrelated false positive: '+title);
  }
});

test('Stop legitimate provider host being used for wrong employers',()=>{
  const lever=sample(PILOT_SOURCES[1],{id:'123',text:'WordPress Developer',hostedUrl:'https://jobs.lever.co/other-employer/123'});
  assert.equal(isValidJob(lever),false,'unrelated Lever tenant should be blocked');
  const ashby=sample(PILOT_SOURCES[2],{title:'Website Engineer',jobUrl:'https://jobs.ashbyhq.com/other-org/123',isListed:true});
  assert.equal(isValidJob(ashby),false,'unrelated Ashby tenant should be blocked');
  const greenhouse=sample(PILOT_SOURCES[0],{id:123,title:'WooCommerce Developer',absolute_url:'https://job-boards.greenhouse.io/otherboard/jobs/123'});
  assert.equal(isValidJob(greenhouse),false,'unrelated Greenhouse tenant should be blocked');
});

test('Accept exact employer tenant and reject lookalike domain/path',()=>{
  assert.equal(isValidJob(sample(PILOT_SOURCES[1],{id:'123',text:'WordPress Developer',hostedUrl:'https://jobs.lever.co/kinsta/123'})),true);
  assert.equal(isValidJob(sample(PILOT_SOURCES[2],{title:'Web Developer',jobUrl:'https://jobs.ashbyhq.com/zapier/123',isListed:true})),true);
  assert.equal(isValidJob(sample(PILOT_SOURCES[0],{id:123,title:'Web Developer',absolute_url:'https://job-boards.greenhouse.io/automatticcareers/jobs/123'})),true);
  assert.equal(isValidJob(sample(PILOT_SOURCES[1],{id:'123',text:'Web Developer',hostedUrl:'https://jobs.lever.co.evil.example/kinsta/123'})),false);
});

test('Unrelated generic career pages cannot suppress genuine distinct vacancies',()=>{
  const data=buildRegisterIndex(
    [['vacancy_id','status','','','','','canonical_url','official_url'],['x','shown','','','','','https://kinsta.com/careers','']],
    [['vacancy_id','prepared_at','status','application_route','application_url']],
    [['event_id','vacancy_id','occurred_at','event_type','source','status_after']]
  );
  assert.deepEqual(strongRoleKeys('https://kinsta.com/careers'),[]);
  assert.deepEqual(matchRegister({url:'https://jobs.lever.co/kinsta/123',source_url:'',source_id:'lever',source_job_id:'123',identity:'lever:kinsta:123'},data),{known:false,applied:false});
});

test('Do not treat a prepared draft as a submitted application',()=>{
  const rows=[['vacancy_id','prepared_at','status','application_route','application_url'],['abc','','prepared','','https://jobs.lever.co/kinsta/123']];
  const index=buildRegisterIndex([['vacancy_id','status','','','','','canonical_url','official_url']],rows,[['event_id','vacancy_id','occurred_at','event_type','source','status_after']]);
  assert.equal(matchRegister({url:'https://jobs.lever.co/kinsta/123',source_url:''},index).applied,false);
});

test('Source timestamps never become an invented publication timestamp',()=>{
  const a=sample(PILOT_SOURCES[2],{title:'Web Developer',jobUrl:'https://jobs.ashbyhq.com/zapier/123',isListed:true,publishedAt:'2026-10-15T12:00:00Z'});
  const row=toRadarRow(a,'2026-10-15T20:00:00Z','run-1');
  assert.equal(row.length,21);
  assert.equal(row[10],'');
  assert.equal(row[11],'2026-10-15T20:00:00Z');
  assert.equal(row[14],'ontdekt');
  assert.equal(row[16],'niet_beoordeeld');
});

test('Never persist URL credentials, non-HTTPS or malformed job URLs',()=>{
  for(const raw of ['http://jobs.lever.co/kinsta/123','https://user:password@jobs.lever.co/kinsta/123','javascript:alert(1)','not a URL']){
    assert.equal(canonicalUrl(raw),'');
  }
});


test('reject mismatched provider job IDs even on the right ATS tenant',()=>{
  const lever=sample(PILOT_SOURCES[1],{
    id:'expected',text:'WordPress Developer',
    hostedUrl:'https://jobs.lever.co/kinsta/different'
  });
  assert.equal(isValidJob(lever),false,'Lever URL points to a different job than provider ID');
  const greenhouse=sample(PILOT_SOURCES[0],{
    id:123,title:'Web Developer',
    absolute_url:'https://job-boards.greenhouse.io/automatticcareers/jobs/999'
  });
  assert.equal(isValidJob(greenhouse),false,'Greenhouse URL points to a different job than provider ID');
});

test('public source diagnostics are useful but never print provider-supplied secrets',()=>{
  for(const value of ['Public API fetch timeout_or_network',
    'Public API fetch malformed_result','Public API contract mismatch',
    'Public API adapter internal failure']){
    assert.equal(safeDiagnosticError(new Error(value)),value);
  }
  assert.equal(safeDiagnosticError(new Error('https://private.example/?token=secret')),
    'Unexpected runtime failure');
});
