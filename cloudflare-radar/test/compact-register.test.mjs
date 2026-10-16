import test from 'node:test';
import assert from 'node:assert/strict';
import {REGISTER_COMPACT_RANGES,expandRegisterRanges} from '../src/compact-register.mjs';
import {buildRegisterIndex,sourceActive,activeSourcePairs,PILOT_SOURCES} from '../src/logic.mjs';

function project(rows,from,to){
  return rows.map(row=>row.slice(from,to+1));
}
test('request only 10 strictly necessary columns; reconstruct original register semantics',()=>{
  const sources=[['source_id',...Array(11).fill(''),'status'],
    ['lever',...Array(11).fill(''),'active'],
    ['company-kinsta',...Array(11).fill(''),'active']];
  const vacancies=[['vacancy_id','status','','','','','canonical_url','official_url'],
    ['vone','submitted','','','','','https://jobs.lever.co/kinsta/role-one',''],
    ['vtwo','shown','','','','','https://jobs.lever.co/kinsta/role-two','']];
  const applications=[['vacancy_id','','status','','application_url'],
    ['vone','','submitted','','https://jobs.lever.co/kinsta/role-one/apply']];
  const events=[['event_id','vacancy_id','','event_type','','status_after'],
    ['eone','vone','','submitted','','submitted']];
  const chunks=[project(sources,0,0),project(sources,12,12),
    project(vacancies,0,1),project(vacancies,6,7),
    project(applications,0,0),project(applications,2,2),project(applications,4,4),
    project(events,0,1),project(events,3,3),project(events,5,5)];
  const [s,v,a,e]=expandRegisterRanges(chunks);
  assert.equal(REGISTER_COMPACT_RANGES.length,10);
  assert.equal(REGISTER_COMPACT_RANGES.join('|').includes('A1:M'),false);
  assert.deepEqual(activeSourcePairs(s,PILOT_SOURCES),[PILOT_SOURCES[1]]);
  assert.equal(sourceActive(s,PILOT_SOURCES[1]),true);
  const oldIndex=buildRegisterIndex(vacancies,applications,events);
  const newIndex=buildRegisterIndex(v,a,e);
  assert.deepEqual([...newIndex.applied].sort(),[...oldIndex.applied].sort());
  assert.deepEqual([...newIndex.known].sort(),[...oldIndex.known].sort());
});
test('missing cells in the middle retain physical row numbers to avoid misattributed applications',()=>{
  const chunks=Array.from({length:10},()=>[]);
  chunks[0]=[['source_id'],[],['lever']];
  chunks[1]=[['status'],[],['active']];
  const [rows]=expandRegisterRanges(chunks);
  assert.equal(rows.length,3);
  assert.equal(rows[1][0],undefined);
  assert.equal(rows[2][0],'lever');
  assert.equal(rows[2][12],'active');
});
test('unexpected register response shape stops before dedupe or writes',()=>{
  assert.throws(()=>expandRegisterRanges([]),/Spreadsheet header mismatch/);
  assert.throws(()=>expandRegisterRanges([[],[]]),/Spreadsheet header mismatch/);
});
