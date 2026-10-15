import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync} from 'node:crypto';
import {tick} from '../src/index.mjs';

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
const {privateKey}=generateKeyPairSync('rsa',{modulusLength:2048,privateKeyEncoding:{type:'pkcs8',format:'pem'},publicKeyEncoding:{type:'spki',format:'pem'}});
test('bootstrap, role dedupe, subsequent application and API cooldown',async()=>{
  const saved=globalThis.fetch;
  const results=[],logs=[],db=new FakeD1();let phase=0;
  globalThis.fetch=async(input,options={})=>{
    const url=String(input);
    if(url==='https://oauth2.googleapis.com/token')return Response.json({access_token:'mock-token',expires_in:3600});
    if(url.includes('/values:batchGet')&&url.includes('register-demo')){
      return Response.json({valueRanges:[{values:registry},{values:vacancies},{values:applications},{values:events}]});
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
    assert.equal(results[0][13],'eerder_gesolliciteerd');
    assert.equal(results[0][17],'niet_opnieuw_aanbevelen');
    phase=3;
    assert.equal((await tick(env)).errors,1,'rate limit creates a visible error');
    assert.ok(Date.parse(db.meta.get('cooldown:lever:kinsta'))>Date.now()+14*60000);
    assert.equal((await tick(env)).errors,0,'cooldown skips source fetch');
    assert.ok(db.maxBindings<=100);
    assert.ok(logs.some(row=>row[5]===1&&row[6]===2&&row[7]===1),'correct Runs counters');
    assert.equal(db.meta.get('exclusive_poll_lease'),'1970-01-01T00:00:00.000Z');
  }finally{globalThis.fetch=saved;}
});
test('disabled worker does not access storage/network',async()=>{
  assert.deepEqual(await tick({RADAR_ENABLED:'0'}),{status:'disabled'});
});
