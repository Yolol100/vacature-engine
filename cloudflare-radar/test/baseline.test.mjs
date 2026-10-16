import test from 'node:test';
import assert from 'node:assert/strict';
import {PILOT_SOURCES} from '../src/logic.mjs';
import {CONTROL_KEY,RECEIPT_KEY,runControlledBaseline} from '../src/baseline.mjs';

const now=Date.parse('2026-10-16T12:05:20.000Z');
const id='limited_baseline_20261016';
class DB{
  constructor(){this.meta=new Map();this.obs=new Map();this.calls=0;}
  prepare(sql){return {bind:(...p)=>({
    first:async()=>{
      this.calls++;
      if(sql.startsWith('SELECT value FROM radar_metadata'))return this.meta.has(p[0])?{value:this.meta.get(p[0])}:null;
      if(sql.startsWith('SELECT COUNT(*) AS n FROM radar_observations WHERE source_instance=?')){
        const n=(this.obs.get(p[0])||[]).filter(x=>p.length<2||x===p[1]).length;
        return {n};
      }
      throw Error('Unexpected query '+sql);
    },
    run:async()=>{
      this.calls++;
      if(sql.startsWith('INSERT INTO radar_metadata(name,value)')){
        this.meta.set(p[0],p[1]);return {meta:{changes:1}};
      }
      if(sql.startsWith('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')){
        const changed=Number(this.meta.get(p[1])===p[2]);
        if(changed)this.meta.set(p[1],p[0]);
        return {meta:{changes:changed}};
      }
      throw Error('Unexpected write '+sql);
    }
  })};}
}
const control=(stage=0,expire=now+9*60*1000)=>JSON.stringify({id,stage,expires_at:new Date(expire).toISOString()});
function setup(options={}){
  const db=new DB(),calls=[];
  db.meta.set(CONTROL_KEY,control());
  const env={RADAR_ENABLED:'0',RADAR_DB:db,GOOGLE_SERVICE_ACCOUNT_JSON:'sentinel'};
  const ops={
    now:()=>options.clock??now,
    PILOT_SOURCES,
    tick:async tickEnv=>{
      assert.equal(tickEnv.RADAR_ENABLED,'1');
      assert.equal(env.RADAR_ENABLED,'0','live flag never modified');
      const instance=tickEnv.BASELINE_SOURCE_INSTANCE;
      assert.ok(PILOT_SOURCES.some(x=>x.source_id+':'+x.account===instance));
      calls.push(instance);
      if(options.failStage===calls.length-1)return {status:'partial',sources:0,observations:0,errors:1,new_records:0,applied_reconciled:0};
      db.meta.set('seeded:'+instance,new Date(now).toISOString());
      db.obs.set(instance,['baseline','baseline','baseline']);
      return {status:'ok',sources:1,observations:3,new_records:0,applied_reconciled:0,errors:0};
    }
  };
  return {db,calls,env,ops};
}
test('off by default; no armed record means no D1 or source side effect',async()=>{
  const h=setup();h.db.meta.delete(CONTROL_KEY);
  assert.deepEqual(await runControlledBaseline(h.env,h.ops),{status:'disabled'});
  assert.equal(h.calls.length,0);
});
test('three real ingestion invocations are bounded, staged and idempotent',async()=>{
  const h=setup();
  for(let i=0;i<3;i++){
    const out=await runControlledBaseline(h.env,h.ops);
    assert.equal(out.status,i===2?'ok':'in_progress');
    assert.equal(out.stage,i+1);
    assert.equal(out.source,PILOT_SOURCES[i].source_id+':'+PILOT_SOURCES[i].account);
    assert.equal(out.observations,3);
  }
  assert.equal(h.env.RADAR_ENABLED,'0');
  assert.equal(h.db.meta.get(CONTROL_KEY),'done:'+id);
  assert.equal(JSON.parse(h.db.meta.get(RECEIPT_KEY)).sources.length,3);
  assert.equal((await runControlledBaseline(h.env,h.ops)).status,'disabled');
  assert.equal(h.calls.length,3);
});
test('partial source failure ends trial without silently retrying a fourth Cron',async()=>{
  const h=setup({failStage:1});
  await runControlledBaseline(h.env,h.ops);
  const result=await runControlledBaseline(h.env,h.ops);
  assert.equal(result.status,'failed');
  assert.equal(h.db.meta.get(CONTROL_KEY),'failed:'+id);
  assert.equal(h.calls.length,2);
  assert.equal(JSON.parse(h.db.meta.get(RECEIPT_KEY)).sources[1].status,'failed');
  assert.equal((await runControlledBaseline(h.env,h.ops)).status,'disabled');
});
test('stale, excessive, expired and malformed control records cannot start',async()=>{
  for(const state of ['not json',control(0,now+14*60*1000),control(0,now-1),
    control(3,now+5000)]){
    const h=setup();h.db.meta.set(CONTROL_KEY,state);
    const result=await runControlledBaseline(h.env,h.ops);
    assert.ok(['invalid_control','invalid_or_expired_control'].includes(result.status));
    assert.equal(h.calls.length,0);
  }
});
test('live production enabled prevents private diagnostic',async()=>{
  const h=setup();
  assert.equal((await runControlledBaseline({...h.env,RADAR_ENABLED:'1'},h.ops)).status,'disabled');
  assert.equal(h.calls.length,0);
});
test('preexisting seeded or observation source fails closed',async()=>{
  for(const situation of ['seed','observation']){
    const h=setup();
    if(situation==='seed')h.db.meta.set('seeded:greenhouse:automatticcareers','earlier');
    else h.db.obs.set('greenhouse:automatticcareers',['baseline']);
    const out=await runControlledBaseline(h.env,h.ops);
    assert.equal(out.status,'failed');
    assert.equal(h.calls.length,0);
    assert.equal(h.db.meta.get(CONTROL_KEY),'failed:'+id);
  }
});
test('parallel invocations cannot run the same stage twice',async()=>{
  const h=setup();
  const a=await Promise.all([runControlledBaseline(h.env,h.ops),runControlledBaseline(h.env,h.ops)]);
  assert.equal(a.filter(x=>x.status==='in_progress').length,1);
  assert.equal(h.calls.length,1);
});
