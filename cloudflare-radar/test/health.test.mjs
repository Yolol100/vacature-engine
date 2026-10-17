import test from 'node:test';
import assert from 'node:assert/strict';
import {monitoredTick,safeDiagnosticError} from '../src/health.mjs';

class DB{
  constructor(){this.state=new Map();this.calls=0;}
  prepare(sql){return {bind:(...args)=>({
    first:async()=>{this.calls++;return this.state.has(args[0])?{value:this.state.get(args[0])}:null;},
    run:async()=>{
      this.calls++;assert.match(sql,/^INSERT INTO radar_metadata/);
      this.state.set(args[0],args[1]);return {meta:{changes:1}};
    }
  })};}
}
const now=Date.parse('2026-10-16T11:56:00.000Z');
test('disabled flag never fetches or writes health state',async()=>{
  const db=new DB(),env={RADAR_ENABLED:'0',RADAR_DB:db};
  const out=await monitoredTick(env,async()=>{throw Error('MUST NOT RUN')},()=>now);
  assert.equal(out.status,'disabled');
  assert.equal(db.calls,0);
});
test('healthy poll records UTC heartbeat and redacted counters',async()=>{
  const db=new DB(),env={RADAR_ENABLED:'1',RADAR_DB:db};
  const r=await monitoredTick(env,async()=>({status:'ok',sources:1,new_records:0,errors:0}),()=>now);
  assert.equal(r.status,'ok');
  assert.equal(db.state.get('health:last_ok_utc'),'2026-10-16T11:56:00.000Z');
  assert.equal(JSON.parse(db.state.get('health:last_result')).delivered,0);
});
test('missing more than six Cron minutes is recorded when schedule resumes',async()=>{
  const db=new DB(),env={RADAR_ENABLED:'1',RADAR_DB:db};
  db.state.set('health:last_started_utc',new Date(now-8*60000).toISOString());
  await monitoredTick(env,async()=>({status:'cooldown'}),()=>now);
  const gap=JSON.parse(db.state.get('health:last_gap'));
  assert.equal(gap.gap_minutes,8);
  assert.equal(gap.detected_at,'2026-10-16T11:56:00.000Z');
});
test('partial ATS error stores health incident and does not alter response',async()=>{
  const db=new DB(),env={RADAR_ENABLED:'1',RADAR_DB:db};
  const result=await monitoredTick(env,async()=>({status:'partial',errors:1,sources:0}),()=>now);
  assert.equal(result.status,'partial');
  assert.match(db.state.get('health:last_failure'),/Partial ATS poll/);
  assert.ok(!db.state.has('health:last_ok_utc'));
});
test('secret-bearing runtime exception is not persisted to health metadata',async()=>{
  const db=new DB(),env={RADAR_ENABLED:'1',RADAR_DB:db};
  const error=new Error('service JSON malformed: PRIVATE KEY SENSITIVE');
  await assert.rejects(monitoredTick(env,async()=>{throw error},()=>now),x=>x===error);
  assert.ok(!JSON.stringify([...db.state]).includes('PRIVATE KEY SENSITIVE'));
  assert.equal(JSON.parse(db.state.get('health:last_result')).status,'failed');
});

test('safe diagnostic allows only bounded Sheets source and reason',()=>{
  assert.equal(safeDiagnosticError(new Error('Sheets read HTTP 403 [radar:PERMISSION_DENIED]')),
    'Sheets read HTTP 403 [radar:PERMISSION_DENIED]');
  assert.equal(safeDiagnosticError(new Error('Sheets read HTTP 403 [register:SCOPE_INSUFFICIENT]')),
    'Sheets read HTTP 403 [register:SCOPE_INSUFFICIENT]');
  assert.equal(safeDiagnosticError(new Error('Sheets read HTTP 403 [private:secret@example.invalid]')),
    'Unexpected runtime failure');
  assert.equal(safeDiagnosticError(new Error('Sheets read HTTP 403 [radar:PERMISSION_DENIED] PRIVATE_KEY')),
    'Unexpected runtime failure');
});
