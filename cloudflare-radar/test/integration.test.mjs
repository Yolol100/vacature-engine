import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync} from 'node:crypto';
import {tick} from '../src/index.mjs';

class FakeD1 {
  constructor(){this.observations=new Map();this.meta=new Map();}
  prepare(sql) {
    return {bind:(...args)=>({
      first:async()=>{
        if(sql.startsWith('SELECT value'))return this.meta.has(args[0])?{value:this.meta.get(args[0])}:null;
        throw new Error('Unhandled D1 first: '+sql);
      },
      all:async()=>{
        if(sql.startsWith('SELECT identity,canonical_url'))return {results:[...this.observations.values()].filter(x=>x.status===args[0]).slice(0,args[1])};
        if(sql.startsWith('SELECT identity'))return {results:args.filter(id=>this.observations.has(id)).map(identity=>({identity}))};
        throw new Error('Unhandled D1 all: '+sql);
      },
      run:async()=>{
        if(sql.startsWith('INSERT OR IGNORE INTO radar_metadata')){
          const change=!this.meta.has(args[0])?1:0;
          if(change)this.meta.set(args[0],args[1]);
          return {meta:{changes:change}};
        }
        if(sql.startsWith('UPDATE radar_metadata SET value=')){
          const change=sql.includes('value<?')?(this.meta.get(args[1])<args[2]):this.meta.get(args[1])===args[2];
          if(change)this.meta.set(args[1],args[0]);
          return {meta:{changes:change?1:0}};
        }
        if(sql.startsWith('INSERT OR IGNORE INTO radar_observations')){
          for(let i=0;i<args.length;i+=6)if(!this.observations.has(args[i])){
            this.observations.set(args[i],{identity:args[i],source_instance:args[i+1],canonical_url:args[i+2],status:args[i+3],payload_json:args[i+4],first_seen_at:args[i+5]});
          }
          return {meta:{changes:1}};
        }
        if(sql.startsWith('UPDATE radar_observations SET status')){
          for(const id of args.slice(1))this.observations.get(id).status=args[0];
          return {meta:{changes:1}};
        }
        throw new Error('Unhandled D1 run: '+sql);
      }
    })};
  }
}
const registry=[['source_id',...Array(11).fill(''),'status'],['lever',...Array(11).fill(''),'active'],['company-kinsta',...Array(11).fill(''),'active']];
const applications=[['vacancy_id','','status','','application_url'],['vsubmitted','','submitted','','https://jobs.lever.co/kinsta/applied']];
const vacancies=[['vacancy_id','status','','','','','canonical_url','official_url'],['vshown','shown','','','','','https://jobs.lever.co/kinsta/shown','']];
const makeJob=id=>({id,text:'Remote WordPress Developer',hostedUrl:'https://jobs.lever.co/kinsta/'+id,categories:{location:'Remote'}});
const {privateKey}=generateKeyPairSync('rsa',{modulusLength:2048,privateKeyEncoding:{type:'pkcs8',format:'pem'},publicKeyEncoding:{type:'spki',format:'pem'}});
test('bootstrap, new posting, history exclusion and Sheets idempotence',async()=>{
  const savedFetch=globalThis.fetch;
  let phase=0;
  const rows=[];
  globalThis.fetch=async(input,options={})=>{
    const url=String(input);
    if(url==='https://oauth2.googleapis.com/token')return Response.json({access_token:'fake-token',expires_in:3600});
    if(url.includes('/values:batchGet')&&url.includes('register-demo'))return Response.json({valueRanges:[{values:registry},{values:vacancies},{values:applications}]});
    if(url.includes('/values:batchGet')&&url.includes('radar-demo'))return Response.json({valueRanges:[{values:[['observation_key'],...rows.map(r=>[r[0]])]},{values:[['officiele_url'],...rows.map(r=>[r[5]])]}]});
    if(url.includes('api.lever.co/v0/postings/kinsta'))return Response.json(phase===0?[makeJob('historical')]:[makeJob('historical'),makeJob('new'),makeJob('applied'),makeJob('shown')]);
    if(url.includes(':append')){
      const values=JSON.parse(options.body).values;
      if(url.includes('Nieuwe%20vacatures'))rows.push(...values);
      else if(!url.includes('Runs!'))throw new Error('Unexpected append range');
      return Response.json({updates:{updatedRows:values.length}});
    }
    throw new Error('Unexpected network request: '+url);
  };
  try {
    const db=new FakeD1();
    const env={RADAR_ENABLED:'1',RADAR_DB:db,GOOGLE_SERVICE_ACCOUNT_JSON:JSON.stringify({client_email:'service@example.org',private_key:privateKey}),VACATURE_REGISTER_ID:'register-demo',RADAR_RESULT_ID:'radar-demo'};
    assert.equal((await tick(env)).new_records,0);
    phase=1;
    assert.equal((await tick(env)).new_records,1);
    assert.equal(rows.length,1);
    assert.equal(rows[0][5],'https://jobs.lever.co/kinsta/new');
    assert.equal(rows[0][10],'');
    assert.equal(rows[0][13],'onbekend');
    assert.equal((await tick(env)).new_records,0);
    assert.equal(rows.length,1);
    assert.equal(db.observations.get('lever:kinsta:shown').status,'excluded');
    assert.equal(db.observations.get('lever:kinsta:applied').status,'excluded');
    assert.equal(db.meta.get('exclusive_poll_lease'),'1970-01-01T00:00:00.000Z');
  } finally {globalThis.fetch=savedFetch;}
});
