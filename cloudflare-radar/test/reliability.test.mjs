import test from 'node:test';
import assert from 'node:assert/strict';
import {PILOT_SOURCES,sourceActive} from '../src/logic.mjs';
import {RELIABILITY_REQUEST_KEY,RELIABILITY_RESULT_KEY,runReliabilityProbe,safeDiagnosticError} from '../src/reliability.mjs';

class FakeD1{
  constructor(){this.meta=new Map();this.writes=0;}
  prepare(sql){return {bind:(...p)=>({
    first:async()=>{
      assert.ok(sql.startsWith('SELECT value FROM radar_metadata'));
      return this.meta.has(p[0])?{value:this.meta.get(p[0])}:null;
    },
    run:async()=>{
      if(sql.startsWith('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')){
        const change=Number(this.meta.get(p[1])===p[2]);
        if(change){this.meta.set(p[1],p[0]);this.writes++;}
        return {meta:{changes:change}};
      }
      if(sql.startsWith('INSERT INTO radar_metadata(name,value)')){
        this.meta.set(p[0],p[1]);this.writes++;
        return {meta:{changes:1}};
      }
      throw new Error('Unexpected SQL in read-only source probe: '+sql);
    }
  })};}
}
const id='reliability_one_time_20261016';
const statuses=[
  ['source_id',...Array(11).fill(''),'status'],
  ...['greenhouse','lever','ashby','company-automattic','company-kinsta','company-zapier']
    .map(x=>[x,...Array(11).fill(''),'active'])
];
function harness(config={}){
  const db=new FakeD1(),calls=[],reads=[];
  const env={RADAR_ENABLED:'0',RADAR_DB:db,GOOGLE_SERVICE_ACCOUNT_JSON:'mock-service-account',
    VACATURE_REGISTER_ID:'register-demo',RADAR_RESULT_ID:'radar-demo'};
  const ops={
    now:()=>config.time||Date.parse('2026-10-16T11:50:00Z'),
    PILOT_SOURCES,sourceActive,
    accessToken:async()=> 'mock-token',
    readRanges:async(file,ranges,token)=>{
      assert.equal(token,'mock-token');reads.push({file,ranges});
      if(file==='register-demo')return [statuses,[['vacancy_id']],[['vacancy_id']],[['event_id']]];
      assert.equal(file,'radar-demo');
      return [[['observation_key']],[['officiele_url']],[['sollicitatiehistorie']],[['actie']]];
    },
    assertSheetHeaders:(sources,vacancies,applications,events,keys,urls,statusCols,actions)=>{
      assert.equal(sources[0][0],'source_id');
      assert.equal(vacancies[0][0],'vacancy_id');
      assert.equal(applications[0][0],'vacancy_id');
      assert.equal(events[0][0],'event_id');
      assert.equal(keys[0][0],'observation_key');
      assert.equal(urls[0][0],'officiele_url');
      assert.equal(statusCols[0][0],'sollicitatiehistorie');
      assert.equal(actions[0][0],'actie');
    },
    publicJobs:async(source)=>{
      calls.push(source.source_id);
      if(source.source_id===config.failSource)throw new Error('Public API HTTP 429');
      return Array.from({length:config.zeroSource===source.source_id?0:source.source_id==='greenhouse'?12:3},
        (_,i)=>({source_id:source.source_id,source_job_id:String(i)}));
    }
  };
  db.meta.set(RELIABILITY_REQUEST_KEY,id+':0');
  return {env,db,ops,calls,reads};
}
test('default disabled and expiry do not touch storage or ATS',async()=>{
  const x=harness();
  x.db.meta.delete(RELIABILITY_REQUEST_KEY);
  assert.deepEqual(await runReliabilityProbe(x.env,x.ops),{status:'disabled'});
  assert.equal(x.calls.length,0);
  x.db.meta.set(RELIABILITY_REQUEST_KEY,id+':0');
  assert.equal((await runReliabilityProbe({...x.env,RADAR_ENABLED:'1'},x.ops)).status,'disabled');
  assert.equal((await runReliabilityProbe(x.env,{...x.ops,now:()=>Date.parse('2026-10-19T00:00:00Z')})).status,'disabled');
  assert.equal(x.db.writes,0);
});

test('three independent Cron stages check only their official ATS and never edit Sheets',async()=>{
  const x=harness();
  for(let i=0;i<3;i++){
    const result=await runReliabilityProbe(x.env,x.ops);
    assert.equal(result.stage,i+1);
    assert.equal(result.status,i===2?'ok':'in_progress');
    assert.equal(x.calls.length,i+1);
    assert.equal(x.reads.length,(i+1)*2);
  }
  assert.deepEqual(x.calls,['greenhouse','lever','ashby']);
  const receipt=JSON.parse(x.db.meta.get(RELIABILITY_RESULT_KEY));
  assert.equal(receipt.status,'ok');
  assert.deepEqual(Object.keys(receipt.sources),[
    'greenhouse:automatticcareers','lever:kinsta','ashby:zapier'
  ]);
  assert.equal(receipt.sources['greenhouse:automatticcareers'].observations,12);
  assert.equal(receipt.sources['lever:kinsta'].observations,3);
  assert.equal(receipt.sources['ashby:zapier'].observations,3);
  assert.equal(x.db.meta.get(RELIABILITY_REQUEST_KEY),'done:'+id);
  assert.equal((await runReliabilityProbe(x.env,x.ops)).status,'disabled');
  assert.equal(x.calls.length,3);
});

test('ATS 429 is reported as partial; neither repeated nor retried immediately',async()=>{
  const x=harness({failSource:'lever'});
  for(let i=0;i<3;i++)await runReliabilityProbe(x.env,x.ops);
  const receipt=JSON.parse(x.db.meta.get(RELIABILITY_RESULT_KEY));
  assert.equal(receipt.status,'partial');
  assert.equal(receipt.sources['lever:kinsta'].status,'failed');
  assert.equal(receipt.sources['lever:kinsta'].error,'Public API HTTP 429');
  assert.equal(x.calls.filter(x=>x==='lever').length,1);
});

test('empty first snapshot is not accepted as healthy',async()=>{
  const x=harness({zeroSource:'greenhouse'});
  await runReliabilityProbe(x.env,x.ops);
  const receipt=JSON.parse(x.db.meta.get(RELIABILITY_RESULT_KEY));
  assert.equal(receipt.sources['greenhouse:automatticcareers'].status,'failed');
  assert.equal(receipt.sources['greenhouse:automatticcareers'].error,'Empty first ATS snapshot');
});

test('concurrent invocation atomically claims one stage',async()=>{
  const x=harness();
  const outcomes=await Promise.all([runReliabilityProbe(x.env,x.ops),runReliabilityProbe(x.env,x.ops)]);
  assert.equal(outcomes.filter(x=>x.status==='in_progress').length,1);
  assert.equal(x.calls.length,1);
});

test('stale checkpoint and secret-bearing error messages fail closed',async()=>{
  const x=harness();
  x.db.meta.set(RELIABILITY_REQUEST_KEY,id+':1');
  assert.equal((await runReliabilityProbe(x.env,x.ops)).status,'invalid_checkpoint');
  assert.equal(x.calls.length,0);
  assert.equal(safeDiagnosticError(new Error('Invalid key: PRIVATE KEY SECRET')), 'Unexpected runtime failure');
});
