import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/index.mjs';

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
test('no public HTTP endpoint',async()=>{
  const result=await worker.fetch();
  assert.equal(result.status,404);
});
