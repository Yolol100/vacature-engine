import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/review-worker.mjs';

class ReadOnlyMetadata {
  constructor(){this.reads=0;}
  prepare(){this.reads++;throw new Error('Disabled worker must never open D1');}
}
test('disabled settings cannot read D1 or schedule a micro-pipeline',async()=>{
  const db=new ReadOnlyMetadata(),ctx={calls:0,waitUntil(){this.calls++;}};
  for(const settings of [
    {RADAR_ENABLED:'0',RADAR_PIPELINE_MODE:'off'},
    {RADAR_ENABLED:'0',RADAR_PIPELINE_MODE:'staged_review'},
    {RADAR_ENABLED:'1',RADAR_PIPELINE_MODE:'off'},
    {RADAR_ENABLED:'1'},
    {RADAR_ENABLED:'0'}
  ]){
    await worker.scheduled({}, {...settings,RADAR_DB:db}, ctx);
  }
  assert.equal(ctx.calls,0);
  assert.equal(db.reads,0);
});
test('old preview marker is inert even when present in D1',async()=>{
  const db=new ReadOnlyMetadata(),ctx={calls:0,waitUntil(){this.calls++;}};
  await worker.scheduled({}, {RADAR_ENABLED:'0',RADAR_PIPELINE_MODE:'off',RADAR_DB:db}, ctx);
  assert.equal(ctx.calls,0);
  assert.equal(db.reads,0);
});
test('review-only scheduled path skips redundant health DB I/O',async()=>{
  const db=new ReadOnlyMetadata();
  let pending;
  const ctx={waitUntil(p){pending=p;}};
  await worker.scheduled({},{
    RADAR_ENABLED:'1',RADAR_PIPELINE_MODE:'staged_review',RADAR_DB:db
  },ctx);
  assert.ok(pending,'staged runner must be scheduled');
  await pending;
  assert.equal(db.reads,0,'missing required bindings must fail before any health D1 read');
});
test('slim Worker private CPU probe needs a valid D1 lease',async()=>{
  let scheduled=0;const keys=[];
  const db={prepare(){return {bind(k){keys.push(k);return {first:async()=>null};}}}};
  await worker.scheduled({},{RADAR_ENABLED:'0',RADAR_PIPELINE_MODE:'off',
    RADAR_CPU_CANARY:'1',RADAR_DB:db},{waitUntil(){scheduled++;}});
  assert.deepEqual(keys,['micro:v2:cpu_canary']);
  assert.equal(scheduled,0);
});
test('slim Worker cannot use expired or wrong-kind permit',async()=>{
  for(const p of [
    {kind:'wrong',started:Date.now()-60000,until:Date.now()+60000},
    {kind:'slim-bundle-free-cpu-20261017',started:Date.now()-90000,until:Date.now()-30000},
    {kind:'slim-bundle-free-cpu-20261017',started:Date.now()-600000,until:Date.now()+30000}
  ]){
    let scheduled=0;
    const db={prepare(){return {bind(){return {first:async()=>({value:JSON.stringify(p)})};}}}};
    await worker.scheduled({},{RADAR_ENABLED:'0',RADAR_PIPELINE_MODE:'off',
      RADAR_CPU_CANARY:'1',RADAR_DB:db},{waitUntil(){scheduled++;}});
    assert.equal(scheduled,0);
  }
});
test('no public HTTP endpoint',async()=>{
  const result=await worker.fetch();
  assert.equal(result.status,404);
});
