import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync} from 'node:crypto';
import {tick,cpuReadOnlyTick} from '../src/index.mjs';
import {REGISTER_COMPACT_RANGES} from '../src/compact-register.mjs';

class FakeD1{
  constructor(){this.observations=new Map();this.meta=new Map();this.maxBindings=0;this.statements=0;}
  prepare(sql){
    return {bind:(...args)=>{
      this.statements++;
      this.maxBindings=Math.max(this.maxBindings,args.length);
      if(args.length>100)throw new Error('D1: >100 bound parameters');
      return {
        first:async()=>{
          if(sql.startsWith('SELECT value FROM radar_metadata'))return this.meta.has(args[0])?{value:this.meta.get(args[0])}:null;
          throw new Error('Unhandled D1 first: '+sql);
        },
        all:async()=>{
          if(sql.startsWith('SELECT identity,canonical_url'))return{results:[...this.observations.values()].filter(x=>x.status===args[0]).slice(0,args[1])};
          if(sql.startsWith('SELECT identity'))return{results:args.filter(x=>this.observations.has(x)).map(identity=>({identity}))};
          throw new Error('Unhandled D1 all: '+sql);
        },
        run:async()=>{
          if(sql.startsWith('INSERT OR IGNORE INTO radar_metadata')){
            const changes=this.meta.has(args[0])?0:1;
            if(changes)this.meta.set(args[0],args[1]);
            return{meta:{changes}};
          }
          if(sql.startsWith('UPDATE radar_metadata SET value=? WHERE name=? AND value<?')){
            const changed=this.meta.get(args[1])<args[2];
            if(changed)this.meta.set(args[1],args[0]);
            return{meta:{changes:changed?1:0}};
          }
          if(sql.startsWith('UPDATE radar_metadata SET value=? WHERE name=? AND value=?')){
            const changed=this.meta.get(args[1])===args[2];
            if(changed)this.meta.set(args[1],args[0]);
            return{meta:{changes:changed?1:0}};
          }
          if(sql.startsWith('INSERT INTO radar_metadata(name,value)')){
            this.meta.set(args[0],args[1]);return{meta:{changes:1}};
          }
          if(sql.startsWith('INSERT OR IGNORE INTO radar_observations')){
            for(let i=0;i<args.length;i+=6){
              if(!this.observations.has(args[i]))this.observations.set(args[i],{
                identity:args[i],source_instance:args[i+1],canonical_url:args[i+2],
                status:args[i+3],payload_json:args[i+4],first_seen_at:args[i+5]});
            }
            return{meta:{changes:1}};
          }
          if(sql.startsWith('UPDATE radar_observations SET status')){
            for(const id of args.slice(1))this.observations.get(id).status=args[0];
            return{meta:{changes:args.length-1}};
          }
          throw new Error('Unhandled D1 run: '+sql);
        }
      };
    }};
  }
}
const registry=[['source_id'],['lever',...Array(11).fill(''),'active'],['company-kinsta',...Array(11).fill(''),'active']];
const applications=[['vacancy_id','prepared_at','status','application_route','application_url'],['vsubmitted','','submitted','','https://jobs.lever.co/kinsta/applied']];
const vacancies=[['vacancy_id','status','','','','','canonical_url','official_url'],['vshown','shown','','','','','https://jobs.lever.co/kinsta/shown','']];
const events=[['event_id','vacancy_id','occurred_at','event_type','source','status_after']];
const mkjob=id=>({id,text:'Remote WordPress Developer',hostedUrl:'https://jobs.lever.co/kinsta/'+id,categories:{location:'Remote'}});
function registerBatchResponse(url){
  const sets={'Bronnen':registry,'Vacatures':vacancies,'Applications':applications,'ApplicationEvents':events};
  const ranges=new URL(url).searchParams.getAll('ranges');
  assert.deepEqual(ranges,REGISTER_COMPACT_RANGES);
  const valueRanges=ranges.map(range=>{
    const match=/^'([^']+)'!([A-Z])1:([A-Z])$/.exec(range);
    assert.ok(match,'Unexpected register column request: '+range);
    const rows=sets[match[1]];
    assert.ok(rows,'Unexpected register tab: '+match[1]);
    const start=match[2].charCodeAt(0)-65,end=match[3].charCodeAt(0)-65;
    return {values:rows.map(row=>{
      const chunk=[];
      for(let i=start;i<=end;i++)chunk.push(row[i]??'');
      return chunk;
    })};
  });
  return Response.json({valueRanges});
}

const {privateKey}=generateKeyPairSync('rsa',{modulusLength:2048,privateKeyEncoding:{type:'pkcs8',format:'pem'},publicKeyEncoding:{type:'spki',format:'pem'}});
test('bootstrap, role dedupe, subsequent application and API cooldown',async()=>{
  const saved=globalThis.fetch;
  const results=[],logs=[],db=new FakeD1();let phase=0;
  globalThis.fetch=async(input,options={})=>{
    const url=String(input);
    if(url==='https://oauth2.googleapis.com/token')return Response.json({access_token:'mock-token',expires_in:3600});
    if(url.includes('/values:batchGet')&&url.includes('register-demo')){
      return registerBatchResponse(url);
    }
    if(url.includes('/values:batchGet')&&url.includes('radar-demo')){
      return Response.json({valueRanges:[
        {values:[['observation_key'],...results.map(r=>[r[0]])]},
        {values:[['officiele_url'],...results.map(r=>[r[5]])]},
        {values:[['sollicitatiehistorie'],...results.map(r=>[r[13]])]},
        {values:[['actie'],...results.map(r=>[r[17]])]}
      ]});
    }
    if(url.includes('api.lever.co/v0/postings/kinsta')){
      if(phase===3)return new Response('Too Many Requests',{status:429,headers:{'retry-after':'60'}});
      return Response.json(phase===0?[mkjob('historical')]:[mkjob('historical'),mkjob('new'),mkjob('applied'),mkjob('shown')]);
    }
    if(url.includes('values:batchUpdate')){
      const changes=JSON.parse(options.body).data;
      for(const item of changes){
        const row=Number(item.range.match(/\d+$/)[0])-2;
        if(item.range.includes('!N'))results[row][13]=item.values[0][0];
        else if(item.range.includes('!R'))results[row][17]=item.values[0][0];
        else throw new Error('Unexpected Sheets update cell');
      }
      return Response.json({totalUpdatedCells:changes.length});
    }
    if(url.includes(':append')){
      const values=JSON.parse(options.body).values;
      if(url.includes('Nieuwe%20vacatures'))results.push(...values);
      else if(url.includes('Runs!'))logs.push(...values);
      else throw new Error('Unexpected Sheets append '+url);
      return Response.json({updates:{updatedRows:values.length}});
    }
    throw new Error('Unexpected mock request: '+url);
  };
  try{
    const env={RADAR_ENABLED:'1',RADAR_DB:db,GOOGLE_SERVICE_ACCOUNT_JSON:JSON.stringify({client_email:'service@example.org',private_key:privateKey}),
      VACATURE_REGISTER_ID:'register-demo',RADAR_RESULT_ID:'radar-demo'};
    assert.equal((await tick(env)).new_records,0,'bootstrap should not alert older jobs');
    phase=1;
    assert.equal((await tick(env)).new_records,1);
    assert.equal(results.length,1);
    assert.equal(results[0][5],'https://jobs.lever.co/kinsta/new');
    assert.equal(results[0][10],'','no fabricated publish date');
    assert.equal(db.observations.get('lever:kinsta:applied').status,'excluded');
    assert.equal(db.observations.get('lever:kinsta:shown').status,'excluded');
    assert.equal((await tick(env)).new_records,0,'repeat must not append duplicate');
    assert.equal(results.length,1);
    applications.push(['vnew','','submitted','','https://jobs.lever.co/kinsta/new/apply']);
    events.push(['e-new','vnew','','submitted','','submitted']);
    const changed=await tick(env);
    assert.equal(changed.applied_reconciled,1);
    assert.equal(logs.at(-1)?.[7],1,'later confirmed application must be counted in historical applications');
    assert.equal(results[0][13],'eerder_gesolliciteerd');
    assert.equal(results[0][17],'niet_opnieuw_aanbevelen');
    phase=3;
    assert.equal((await tick(env)).errors,1,'rate limit creates a visible error');
    assert.ok(Date.parse(db.meta.get('cooldown:lever:kinsta'))>Date.now()+14*60000);
    const cooling=await tick(env);
    assert.equal(cooling.errors,0,'cooldown skips source fetch');
    assert.equal(cooling.status,'cooldown','a skipped rate-limited poll must not be logged as successful');
    assert.ok(db.maxBindings<=100);
    assert.ok(logs.some(row=>row[5]===1&&row[6]===1&&row[7]===1),'correct disjoint Runs counters');
    assert.equal(db.meta.get('exclusive_poll_lease'),'1970-01-01T00:00:00.000Z');
  }finally{globalThis.fetch=saved;}
});
test('disabled worker does not access storage/network',async()=>{
  assert.deepEqual(await tick({RADAR_ENABLED:'0'}),{status:'disabled'});
});


test('160 job source stays within free D1 query and SQL binding limits', async()=>{
  const saved=globalThis.fetch, db=new FakeD1();
  const jobs=Array.from({length:160},(_,i)=>mkjob('load-'+i));
  globalThis.fetch=async(input,options={})=>{
    const url=String(input);
    if(url==='https://oauth2.googleapis.com/token')return Response.json({access_token:'mock-token',expires_in:3600});
    if(url.includes('/values:batchGet')&&url.includes('register-demo'))
      return registerBatchResponse(url);
    if(url.includes('/values:batchGet')&&url.includes('radar-demo'))
      return Response.json({valueRanges:[{values:[['observation_key']]},{values:[['officiele_url']]},{values:[['sollicitatiehistorie']]},{values:[['actie']]}]});
    if(url.includes('api.lever.co/v0/postings/kinsta'))return Response.json(jobs);
    if(url.includes('Runs!')&&url.includes(':append'))
      return Response.json({updates:{updatedRows:JSON.parse(options.body).values.length}});
    throw new Error('Unexpected capacity test request: '+url);
  };
  try{
    const result=await tick({RADAR_ENABLED:'1',RADAR_DB:db,
      GOOGLE_SERVICE_ACCOUNT_JSON:JSON.stringify({client_email:'test@example.org',private_key:privateKey}),
      VACATURE_REGISTER_ID:'register-demo',RADAR_RESULT_ID:'radar-demo'});
    assert.equal(result.new_records,0);
    assert.equal(db.observations.size,160);
    assert.ok(db.maxBindings<=100,'D1 supports maximum 100 SQL bound params');
    assert.ok(db.statements<=50,'D1 Free supports maximum 50 queries per Worker execution');
  }finally{globalThis.fetch=saved;}
});


test('ambiguous Sheets append outcome is reconciled without a second vacancy row',async()=>{
  const previousFetch=globalThis.fetch, db=new FakeD1(), rows=[];
  let phase=0,dropResponse=true;
  globalThis.fetch=async(input,options={})=>{
    const url=String(input);
    if(url==='https://oauth2.googleapis.com/token')return Response.json({access_token:'mock-token',expires_in:3600});
    if(url.includes('/values:batchGet')&&url.includes('register-demo')){
      return registerBatchResponse(url);
    }
    if(url.includes('/values:batchGet')&&url.includes('radar-demo')){
      return Response.json({valueRanges:[
        {values:[['observation_key'],...rows.map(r=>[r[0]])]},
        {values:[['officiele_url'],...rows.map(r=>[r[5]])]},
        {values:[['sollicitatiehistorie'],...rows.map(r=>[r[13]])]},
        {values:[['actie'],...rows.map(r=>[r[17]])]}
      ]});
    }
    if(url.includes('api.lever.co/v0/postings/kinsta')){
      return Response.json(phase===0?[mkjob('historical')]:[mkjob('historical'),mkjob('recovery')]);
    }
    if(url.includes(':append')){
      const values=JSON.parse(options.body).values;
      if(url.includes('Nieuwe%20vacatures')){
        rows.push(...values); // The server committed the append.
        if(dropResponse){dropResponse=false;throw new Error('connection lost after server append');}
      }else if(!url.includes('Runs!'))throw new Error('unknown Sheets range');
      return Response.json({updates:{updatedRows:values.length}});
    }
    throw new Error('unknown mock transport: '+url);
  };
  try{
    const env={RADAR_ENABLED:'1',RADAR_DB:db,
      GOOGLE_SERVICE_ACCOUNT_JSON:JSON.stringify({client_email:'fake@example.org',private_key:privateKey}),
      VACATURE_REGISTER_ID:'register-demo',RADAR_RESULT_ID:'radar-demo'};
    assert.equal((await tick(env)).new_records,0);
    phase=1;
    await assert.rejects(tick(env),/connection lost after server append/);
    assert.equal(rows.length,1,'first Sheets append landed despite lost response');
    assert.equal(db.observations.get('lever:kinsta:recovery').status,'pending');
    const outcome=await tick(env);
    assert.equal(outcome.new_records,0,'retry must not append a second row');
    assert.equal(rows.length,1);
    assert.equal(db.observations.get('lever:kinsta:recovery').status,'delivered');
    assert.equal(db.meta.get('exclusive_poll_lease'),'1970-01-01T00:00:00.000Z');
  }finally{globalThis.fetch=previousFetch;}
});


test('overlapping Cron run is skipped before network access',async()=>{
  const db=new FakeD1();
  db.meta.set('exclusive_poll_lease',new Date(Date.now()+60000).toISOString());
  const original=globalThis.fetch;
  globalThis.fetch=async()=>{throw new Error('no network should be attempted');};
  try{
    const outcome=await tick({RADAR_ENABLED:'1',RADAR_DB:db,
      GOOGLE_SERVICE_ACCOUNT_JSON:'{}',VACATURE_REGISTER_ID:'register-demo',RADAR_RESULT_ID:'radar-demo'});
    assert.equal(outcome.status,'overlap_skipped');
    assert.equal(db.observations.size,0);
  }finally{globalThis.fetch=original;}
});

test('schema corruption does not initialize baseline or generate false new jobs',async()=>{
  const db=new FakeD1(),original=globalThis.fetch,updates=[];
  let broken=true;
  globalThis.fetch=async(input,options={})=>{
    const url=String(input);
    if(url==='https://oauth2.googleapis.com/token')return Response.json({access_token:'test-token',expires_in:3600});
    if(url.includes('/values:batchGet')&&url.includes('register-demo')){
      return registerBatchResponse(url);
    }
    if(url.includes('/values:batchGet')&&url.includes('radar-demo')){
      return Response.json({valueRanges:[{values:[['observation_key']]},{values:[['officiele_url']]},
        {values:[['sollicitatiehistorie']]},{values:[['actie']]}]});
    }
    if(url.includes('api.lever.co/v0/postings/kinsta')){
      return broken?Response.json({error:'provider schema changed'}):Response.json([mkjob('existing')]);
    }
    if(url.includes(':append')){
      if(url.includes('Nieuwe%20vacatures'))updates.push(...JSON.parse(options.body).values);
      return Response.json({updates:{updatedRows:JSON.parse(options.body).values.length}});
    }
    throw new Error('Unexpected transport: '+url);
  };
  try{
    const env={RADAR_ENABLED:'1',RADAR_DB:db,
      GOOGLE_SERVICE_ACCOUNT_JSON:JSON.stringify({client_email:'test@example.org',private_key:privateKey}),
      VACATURE_REGISTER_ID:'register-demo',RADAR_RESULT_ID:'radar-demo'};
    const failure=await tick(env);
    assert.equal(failure.status,'partial');
    assert.equal(failure.errors,1);
    assert.equal(db.meta.get('seeded:lever:kinsta'),undefined,'bad response cannot mark a source healthy');
    assert.equal(db.observations.size,0);
    broken=false;
    // Reset only the mock cooldown to simulate the next eligible real poll.
    db.meta.set('cooldown:lever:kinsta','1970-01-01T00:00:00.000Z');
    const recovered=await tick(env);
    assert.equal(recovered.new_records,0,'recovery must seed baseline, not alert historical positions');
    assert.equal(db.observations.get('lever:kinsta:existing').status,'baseline');
    assert.equal(updates.length,0);
  }finally{globalThis.fetch=original;}
});


test('pending outbox from blocked source is never published as a new radar job',async()=>{
  const savedFetch=globalThis.fetch,db=new FakeD1(),resultRows=[];
  const key='ashby:zapier:role-123',url='https://jobs.ashbyhq.com/zapier/role-123';
  db.observations.set(key,{identity:key,source_instance:'ashby:zapier',canonical_url:url,
    status:'pending',payload_json:JSON.stringify([key,'ashby','role-123','Zapier','Web Developer',url,url,
      'Remote','EMEA','','','2026-10-15T19:00:00Z','2026-10-15T19:00:00Z',
      'onbekend','ontdekt','onbekend','niet_beoordeeld','officiele_verificatie_nodig','','','old-run']),
    first_seen_at:'2026-10-15T19:00:00Z'});
  globalThis.fetch=async(input,options={})=>{
    const request=String(input);
    if(request==='https://oauth2.googleapis.com/token')return Response.json({access_token:'fake-token',expires_in:3600});
    if(request.includes('/values:batchGet')&&request.includes('register-demo'))
      return registerBatchResponse(request);
    if(request.includes('/values:batchGet')&&request.includes('radar-demo'))
      return Response.json({valueRanges:[{values:[['observation_key']]},{values:[['officiele_url']]},
        {values:[['sollicitatiehistorie']]},{values:[['actie']]}]});
    if(request.includes('api.lever.co/v0/postings/kinsta'))return Response.json([]);
    if(request.includes(':append')){
      const batch=JSON.parse(options.body).values;
      if(request.includes('Nieuwe%20vacatures'))resultRows.push(...batch);
      return Response.json({updates:{updatedRows:batch.length}});
    }
    throw new Error('Unexpected transport: '+request);
  };
  try{
    const outcome=await tick({RADAR_ENABLED:'1',RADAR_DB:db,
      GOOGLE_SERVICE_ACCOUNT_JSON:JSON.stringify({client_email:'service@example.org',private_key:privateKey}),
      VACATURE_REGISTER_ID:'register-demo',RADAR_RESULT_ID:'radar-demo'});
    assert.equal(outcome.new_records,0);
    assert.equal(resultRows.length,0,'a blocked source cannot leak pending records into the radar');
    assert.equal(db.observations.get(key).status,'excluded');
  }finally{globalThis.fetch=savedFetch;}
});


test('empty first ATS response cannot seed baseline and mislabel recovered vacancies',async()=>{
  const originalFetch=globalThis.fetch, db=new FakeD1(), emitted=[];
  let empty=true;
  globalThis.fetch=async(input,options={})=>{
    const url=String(input);
    if(url==='https://oauth2.googleapis.com/token')return Response.json({access_token:'mock-token',expires_in:3600});
    if(url.includes('/values:batchGet')&&url.includes('register-demo'))return registerBatchResponse(url);
    if(url.includes('/values:batchGet')&&url.includes('radar-demo'))return Response.json({valueRanges:[
      {values:[['observation_key']]},{values:[['officiele_url']]},
      {values:[['sollicitatiehistorie']]},{values:[['actie']]}]});
    if(url.includes('api.lever.co/v0/postings/kinsta'))return Response.json(empty?[]:[mkjob('returned-original')]);
    if(url.includes(':append')){
      const records=JSON.parse(options.body).values;
      if(url.includes('Nieuwe%20vacatures'))emitted.push(...records);
      return Response.json({updates:{updatedRows:records.length}});
    }
    throw new Error('Unexpected transport '+url);
  };
  try{
    const env={RADAR_ENABLED:'1',RADAR_DB:db,
      GOOGLE_SERVICE_ACCOUNT_JSON:JSON.stringify({client_email:'test@example.org',private_key:privateKey}),
      VACATURE_REGISTER_ID:'register-demo',RADAR_RESULT_ID:'radar-demo'};
    const first=await tick(env);
    assert.equal(first.status,'partial','an untrusted empty initial response must raise a recoverable error');
    assert.equal(db.meta.has('seeded:lever:kinsta'),false);
    empty=false;
    db.meta.set('cooldown:lever:kinsta','1970-01-01T00:00:00.000Z');
    const recovered=await tick(env);
    assert.equal(recovered.new_records,0,'reappearing original positions must not alert as newly published');
    assert.equal(db.observations.get('lever:kinsta:returned-original').status,'baseline');
    assert.equal(emitted.length,0);
  }finally{globalThis.fetch=originalFetch;}
});

test('CPU probe reads real auth, register, radar, ATS and D1 without business writes',async()=>{
  const saved=globalThis.fetch,db=new FakeD1();
  let writes=0,reads=0;
  globalThis.fetch=async(input,options={})=>{
    const url=String(input);
    if(url==='https://oauth2.googleapis.com/token')return Response.json({access_token:'cpu-test-token',expires_in:3600});
    if(url.includes('values:batchGet')&&url.includes('register-demo')){reads++;return registerBatchResponse(url);}
    if(url.includes('values:batchGet')&&url.includes('radar-demo')){
      reads++;return Response.json({valueRanges:[{values:[['observation_key']]},
        {values:[['officiele_url']]},{values:[['sollicitatiehistorie']]},{values:[['actie']]}]});
    }
    if(url.includes('api.lever.co/v0/postings/kinsta')){reads++;return Response.json([mkjob('original')]);}
    writes++;throw Error('CPU benchmark must not make any Sheets write');
  };
  try{
    const result=await cpuReadOnlyTick({RADAR_ENABLED:'0',RADAR_DB:db,
      GOOGLE_SERVICE_ACCOUNT_JSON:JSON.stringify({client_email:'local-test@example.org',private_key:privateKey}),
      VACATURE_REGISTER_ID:'register-demo',RADAR_RESULT_ID:'radar-demo'},'lever:kinsta');
    assert.equal(result.status,'ok');
    assert.equal(result.observations,1);
    assert.equal(reads,3);
    assert.equal(writes,0);
    assert.equal(db.observations.size,0);
    assert.equal(db.meta.size,0);
    await assert.rejects(cpuReadOnlyTick({RADAR_ENABLED:'1',RADAR_DB:db},'lever:kinsta'),/Read-only prerequisites/);
  }finally{globalThis.fetch=saved;}
});
