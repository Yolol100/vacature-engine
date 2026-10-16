import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/index.mjs';

class ReadOnlyMetadata {
  constructor(){this.meta=new Map();this.reads=0;}
  prepare(sql){
    assert.match(sql,/^SELECT value FROM radar_metadata/);
    return {bind:key=>({first:async()=>{this.reads++;return this.meta.has(key)?{value:this.meta.get(key)}:null;}})};
  }
}
test('no unarmed private canary can start a Cron while RADAR_ENABLED=0',async()=>{
  const db=new ReadOnlyMetadata(),ctx={calls:0,waitUntil(){this.calls++;}};
  const env={RADAR_ENABLED:'0',RADAR_PIPELINE_MODE:'off',RADAR_DB:db};
  await worker.scheduled({},env,ctx);
  assert.equal(ctx.calls,0);
  assert.equal(db.reads,1);
  db.meta.set('micro:v1:preview_once','not-a-valid-request');
  await worker.scheduled({},env,ctx);
  assert.equal(ctx.calls,0);
  db.meta.set('micro:v1:preview_once','expired_preview_01:'+String(Date.now()-60000));
  await worker.scheduled({},env,ctx);
  assert.equal(ctx.calls,0);
});
test('completed canary cannot automatically start a second D1 cycle',async()=>{
  const db=new ReadOnlyMetadata(),ctx={calls:0,waitUntil(){this.calls++;}};
  const env={RADAR_ENABLED:'0',RADAR_PIPELINE_MODE:'off',RADAR_DB:db};
  db.meta.set('micro:v1:preview_once','preview_once_20261016:'+String(Date.now()+5*60000));
  db.meta.set('micro:v1:control',JSON.stringify({version:1,status:'done',run:'cycle_01'}));
  await worker.scheduled({},env,ctx);
  assert.equal(ctx.calls,0);
});
test('no HTTP endpoint becomes available through the canary',async()=>{
  const r=await worker.fetch();
  assert.equal(r.status,404);
});
