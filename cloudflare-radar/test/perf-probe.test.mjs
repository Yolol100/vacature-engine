import test from 'node:test';
import assert from 'node:assert/strict';
import {runPrivateCpuProbe,PERF_REQUEST,PERF_RESULT} from '../src/perf-probe.mjs';
const now=Date.parse('2026-10-16T11:05:00Z');
const id='cpu_probe_20261016_01';
class DB{
  constructor(){this.meta=new Map();}
  prepare(sql){return {bind:(...args)=>({
    first:async()=>{
      assert.match(sql,/^SELECT value FROM radar_metadata/);
      return this.meta.has(args[0])?{value:this.meta.get(args[0])}:null;
    },
    run:async()=>{
      if(sql.startsWith('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')){
        const changed=Number(this.meta.get(args[1])===args[2]);
        if(changed)this.meta.set(args[1],args[0]);
        return {meta:{changes:changed}};
      }
      if(sql.startsWith('INSERT INTO radar_metadata(name,value)')){
        this.meta.set(args[0],args[1]);return {meta:{changes:1}};
      }
      throw Error('Unexpected D1 statement '+sql);
    }
  })};}
}
function setup(opts={}){
  const db=new DB(),called=[];
  const expires_at=new Date(now+8*60*1000).toISOString();
  db.meta.set(PERF_REQUEST,JSON.stringify({id,stage:0,expires_at}));
  const env={RADAR_ENABLED:'0',RADAR_DB:db};
  const sources=[{source_id:'greenhouse',account:'automatticcareers'},
    {source_id:'lever',account:'kinsta'},{source_id:'ashby',account:'zapier'}];
  const ops={sources,now:()=>opts.time??now,readOnlyTick:async(e,instance)=>{
    assert.equal(e.RADAR_ENABLED,'0');called.push(instance);
    if(opts.failSource===instance)throw Error('Sensitive key leaked');
    return {status:'ok',source:instance,observations:3,already_known:3,new_candidates:0};
  }};
  return {db,called,env,ops};
}
test('not armed means no read-only run',async()=>{
  const x=setup();x.db.meta.delete(PERF_REQUEST);
  assert.equal((await runPrivateCpuProbe(x.env,x.ops)).status,'disabled');
  assert.equal(x.called.length,0);
});
test('one source per minute and exactly three nonrepeating stages',async()=>{
  const x=setup();
  for(let i=0;i<3;i++){
    const v=await runPrivateCpuProbe(x.env,x.ops);
    assert.equal(v.stage,i+1);
    assert.equal(v.status,i===2?'ok':'in_progress');
  }
  assert.deepEqual(x.called,[
    'greenhouse:automatticcareers','lever:kinsta','ashby:zapier']);
  assert.equal(x.db.meta.get(PERF_REQUEST),'done:'+id);
  const receipt=JSON.parse(x.db.meta.get(PERF_RESULT));
  assert.equal(receipt.sources.length,3);
  assert.equal(receipt.status,'ok');
  assert.equal((await runPrivateCpuProbe(x.env,x.ops)).status,'disabled');
});
test('a failure stops and never records sensitive errors',async()=>{
  const x=setup({failSource:'lever:kinsta'});
  await runPrivateCpuProbe(x.env,x.ops);
  assert.equal((await runPrivateCpuProbe(x.env,x.ops)).status,'failed');
  assert.equal(x.db.meta.get(PERF_REQUEST),'failed:'+id);
  assert.equal(x.called.length,2);
  assert.equal(JSON.stringify([...x.db.meta]).includes('Sensitive key'),false);
});
test('malformed, expired and enabled controls fail without running',async()=>{
  for(const token of ['bad-json',JSON.stringify({id,stage:2,expires_at:new Date(now+8*60000).toISOString()}),
    JSON.stringify({id,stage:0,expires_at:new Date(now-1000).toISOString()}),
    JSON.stringify({id,stage:0,expires_at:new Date(now+3600000).toISOString()})]){
    const x=setup();x.db.meta.set(PERF_REQUEST,token);
    const result=await runPrivateCpuProbe(x.env,x.ops);
    assert.ok(['invalid_control','expired_or_invalid','checkpoint_mismatch'].includes(result.status));
    assert.equal(x.called.length,0);
  }
  const y=setup();
  assert.equal((await runPrivateCpuProbe({...y.env,RADAR_ENABLED:'1'},y.ops)).status,'disabled');
  assert.equal(y.called.length,0);
});
test('parallel attempts cannot duplicate the same stage',async()=>{
  const x=setup();
  const outcomes=await Promise.all([runPrivateCpuProbe(x.env,x.ops),runPrivateCpuProbe(x.env,x.ops)]);
  assert.equal(outcomes.filter(v=>v.status==='in_progress').length,1);
  assert.equal(x.called.length,1);
});
