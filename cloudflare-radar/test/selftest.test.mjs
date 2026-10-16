import test from 'node:test';
import assert from 'node:assert/strict';
import {runOneTimeSmokeTest,SMOKE_REQUEST_KEY,SMOKE_RESULT_KEY} from '../src/selftest.mjs';

const REQUEST_ID='smoke_20261016_once';
class FakeD1 {
  constructor(){this.meta=new Map();}
  prepare(sql) {
    return {bind:(...args)=>({
      first:async()=>{
        assert.ok(sql.startsWith('SELECT value FROM radar_metadata'));
        return this.meta.has(args[0])?{value:this.meta.get(args[0])}:null;
      },
      run:async()=>{
        if(sql.startsWith('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')){
          const changes=Number(this.meta.get(args[1])===args[2]);
          if(changes)this.meta.set(args[1],args[0]);
          return {meta:{changes}};
        }
        if(sql.startsWith('INSERT INTO radar_metadata(name,value)')){
          this.meta.set(args[0],args[1]);
          return {meta:{changes:1}};
        }
        throw new Error('Unexpected D1 query: '+sql);
      }
    })};
  }
}
function setup(options={}) {
  const db=new FakeD1(),calls={auth:0,writes:0,clears:0,ats:0};
  let cell=options.occupied?'real user data':null;
  const ops={
    now:()=>Date.parse('2026-10-16T12:00:00Z'),
    accessToken:async()=>{calls.auth++;return 'oauth-token'},
    readRanges:async(id,ranges,token)=>{
      assert.equal(token,'oauth-token');
      if(id==='register-demo'){
        assert.equal(ranges.length,4);
        return [
          [['source_id',...Array(11).fill(''),'status'],['lever',...Array(11).fill(''),'active']],
          [['vacancy_id']], [['vacancy_id']], [['event_id']]
        ];
      }
      assert.equal(id,'radar-demo');
      if(ranges.length===1){
        assert.equal(ranges[0],"'Runs'!L1000");
        return [cell?[[cell]]:[]];
      }
      return [[['observation_key']],[['officiele_url']],[['sollicitatiehistorie']],[['actie']]];
    },
    updateCells:async(id,changes)=>{
      assert.equal(id,'radar-demo');
      assert.equal(changes.length,1);
      assert.equal(changes[0].range,"'Runs'!L1000");
      assert.match(changes[0].value,/^__vacature_radar_selftest__/);
      calls.writes++;
      cell=changes[0].value;
      if(options.lostWriteResponse)throw new Error('connection lost after write');
    },
    clearCell:async(id,range)=>{
      assert.equal(id,'radar-demo');
      assert.equal(range,"'Runs'!L1000");
      calls.clears++;
      cell=null;
    },
    publicJobs:async(source)=>{
      calls.ats++;
      assert.equal(source.account,'kinsta');
      if(options.atsFailure)throw new Error('Public API HTTP 429');
      return [{identity:'lever:kinsta:demo'}];
    },
    assertSheetHeaders:(sources,vacancies,applications,events,keys,urls,statuses,actions)=>{
      assert.equal(sources[0][0],'source_id');
      assert.equal(vacancies[0][0],'vacancy_id');
      assert.equal(applications[0][0],'vacancy_id');
      assert.equal(events[0][0],'event_id');
      assert.equal(keys[0][0],'observation_key');
      assert.equal(urls[0][0],'officiele_url');
      assert.equal(statuses[0][0],'sollicitatiehistorie');
      assert.equal(actions[0][0],'actie');
    },
    PILOT_SOURCES:[{source_id:'lever',account:'kinsta'}],
    sourceActive:()=>true
  };
  const env={RADAR_ENABLED:'0',RADAR_DB:db,
    GOOGLE_SERVICE_ACCOUNT_JSON:'mock-secret-not-real',
    VACATURE_REGISTER_ID:'register-demo',RADAR_RESULT_ID:'radar-demo'};
  return {db,calls,env,ops,getCell:()=>cell};
}

test('no request and enabled production never perform a smoke probe',async()=>{
  const x=setup();
  assert.equal((await runOneTimeSmokeTest(x.env,x.ops)).status,'disabled');
  assert.equal(x.calls.auth,0);
  x.db.meta.set(SMOKE_REQUEST_KEY,REQUEST_ID);
  assert.equal((await runOneTimeSmokeTest({...x.env,RADAR_ENABLED:'1'},x.ops)).status,'disabled');
  assert.equal(x.db.meta.get(SMOKE_REQUEST_KEY),REQUEST_ID);
});

test('one-time smoke checks OAuth, Sheets read/write/clear and exactly one ATS fetch',async()=>{
  const x=setup();
  x.db.meta.set(SMOKE_REQUEST_KEY,REQUEST_ID);
  const first=await runOneTimeSmokeTest(x.env,x.ops);
  assert.deepEqual(first,{status:'ok',google_auth:'ok',sheets_read:'ok',
    sheets_write:'ok',cleanup:'ok',ats:'ok'});
  assert.equal(x.calls.auth,1);
  assert.equal(x.calls.ats,1);
  assert.equal(x.calls.writes,1);
  assert.equal(x.calls.clears,1);
  assert.equal(x.getCell(),null);
  assert.equal(x.db.meta.get(SMOKE_REQUEST_KEY),'done:'+REQUEST_ID);
  const receipt=JSON.parse(x.db.meta.get(SMOKE_RESULT_KEY));
  assert.equal(receipt.status,'ok');
  assert.equal(receipt.ats_job_count,1);
  assert.equal((await runOneTimeSmokeTest(x.env,x.ops)).status,'disabled');
  assert.equal(x.calls.writes,1,'second scheduled event must not repeat');
});

test('an ambiguous Google write response still clears test data and does not retry',async()=>{
  const x=setup({lostWriteResponse:true});
  x.db.meta.set(SMOKE_REQUEST_KEY,REQUEST_ID);
  const result=await runOneTimeSmokeTest(x.env,x.ops);
  assert.equal(result.status,'failed');
  assert.equal(result.cleanup,'ok');
  assert.equal(x.calls.clears,1);
  assert.equal(x.getCell(),null);
  assert.equal(JSON.parse(x.db.meta.get(SMOKE_RESULT_KEY)).error,'Unexpected test failure');
  assert.equal((await runOneTimeSmokeTest(x.env,x.ops)).status,'disabled');
});

test('occupied test cell is never overwritten or removed',async()=>{
  const x=setup({occupied:true});
  x.db.meta.set(SMOKE_REQUEST_KEY,REQUEST_ID);
  assert.equal((await runOneTimeSmokeTest(x.env,x.ops)).status,'failed');
  assert.equal(x.calls.writes,0);
  assert.equal(x.calls.clears,0);
  assert.equal(x.getCell(),'real user data');
});

test('ATS rate limit produces partial receipt after successful Google read/write test',async()=>{
  const x=setup({atsFailure:true});
  x.db.meta.set(SMOKE_REQUEST_KEY,REQUEST_ID);
  const result=await runOneTimeSmokeTest(x.env,x.ops);
  assert.equal(result.status,'partial');
  assert.equal(result.sheets_write,'ok');
  assert.equal(JSON.parse(x.db.meta.get(SMOKE_RESULT_KEY)).ats_error,'Public API HTTP 429');
});
