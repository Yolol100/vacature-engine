import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {selectSupportedSources} from '../src/actions-review.mjs';
import {publicJobs} from '../src/official-ats.mjs';

const manifest=JSON.parse(readFileSync('../ingestion/source-specs.radar.json','utf8'));
const sample={source_id:'greenhouse',adapter:'greenhouse',source_type:'ats',
  account:'automatticcareers',employer:'Automattic',
  options:{registry_source_id:'company-automattic'}};

test('manual Actions review reuses existing radar source specs, not a second source registry',()=>{
  const {sources,unsupported,unverified}=selectSupportedSources(manifest);
  assert.equal(sources.length,12);
  assert.equal(unsupported.length,0);
  assert.deepEqual(unverified,[]);
  assert.deepEqual(sources.map(s=>s.source_id+':'+s.account),[
    'greenhouse:automatticcareers','lever:kinsta','lever:siteground',
    'greenhouse:acquia','greenhouse:gitlab',
    'greenhouse:digitalocean98','greenhouse:pantheon','ashby:zapier',
    'personio:syde','workable:awesomemotive','workable:humanmade',
    'ashby:elevenlabs'
  ]);
  assert.ok(sources.every(s=>s.employer_source_id.startsWith('company-')));
  assert.deepEqual(unsupported,[]);
});

test('invalid tenant, adapter drift, missing owner registration and duplicate sources fail closed',()=>{
  const invalid=[
    [{...sample,account:'https://evil.invalid'}],
    [{...sample,options:{}}],
    [{...sample,adapter:'lever'}],
    [{...sample,source_type:'discovery'}],
    [{...sample,options:{...sample.options,actions_review_host_contract:'weaken'}}],
    [sample,{...sample}],
    [],
    Array.from({length:101},()=>sample)
  ];
  for(const specs of invalid)
    assert.throws(()=>selectSupportedSources(specs),/radar source/);
});

test('nonimplemented adapters never turn into an invented technical provider',()=>{
  const result=selectSupportedSources([sample,{
    source_id:'recruitee',adapter:'recruitee',source_type:'ats',
    account:'humanmade',employer:'Human Made'}]);
  assert.equal(result.sources.length,1);
  assert.deepEqual(result.unsupported,['recruitee']);
});

test('manual review may process a bounded larger source without raising legacy Worker defaults',async()=>{
  const source={source_id:'greenhouse',account:'automatticcareers',employer:'Automattic'};
  const jobs=Array.from({length:200},(_,i)=>({
    id:i+1,title:'WordPress Developer',location:{name:'Remote'},
    absolute_url:'https://job-boards.greenhouse.io/automatticcareers/jobs/'+(i+1)
  }));
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async()=>({
      ok:true,headers:{get:()=>null},text:async()=>JSON.stringify({jobs})
    });
    await assert.rejects(()=>publicJobs(source),/Source exceeds safe job limit/);
    const expanded=await publicJobs(source,{maxJobs:1000,maxBytes:6_000_000});
    assert.equal(expanded.length,200);
    await assert.rejects(()=>publicJobs(source,{maxJobs:2001}),/Invalid bounded ATS limits/);
    await assert.rejects(()=>publicJobs(source,{maxBytes:8_000_000}),/Invalid bounded ATS limits/);
  }finally{globalThis.fetch=original;}
});

test('manual feed max bytes remains bounded independently from job-count allowance',async()=>{
  const original=globalThis.fetch;
  try{
    globalThis.fetch=async()=>({ok:true,headers:{get:()=>String(6_000_001)}});
    await assert.rejects(()=>publicJobs(sample,{maxJobs:1000,maxBytes:6_000_000}),
      /Source payload too large/);
  }finally{globalThis.fetch=original;}
});

test('provider-confirmed custom Greenhouse tenants are present in bounded source scope',()=>{
  const {sources,unverified}=selectSupportedSources(manifest);
  assert.equal(unverified.length,0);
  assert.equal(sources.some(s=>s.account==='digitalocean98'),true);
  assert.equal(sources.some(s=>s.account==='pantheon'),true);
});

test('new official employers must have a bounded registered live tenant',()=>{
  for(const adapter of ['workable','personio']){
    assert.throws(()=>selectSupportedSources([{
      source_id:adapter,adapter,source_type:'ats',
      account:adapter==='personio'?'syde':'awesomemotive',employer:'Example',
      options:{registry_source_id:'../invalid'}
    }]),/Invalid supported radar source specification/);
  }
});

test('official Greenhouse employer-host jobs are accepted without broad domain exceptions',async()=>{
  const cases=[
    {source_id:'greenhouse',account:'digitalocean98',employer:'DigitalOcean',
      id:8249366,url:'https://www.digitalocean.com/careers/position/apply/?gh_jid=8249366'},
    {source_id:'greenhouse',account:'pantheon',employer:'Pantheon',
      id:8202241,url:'https://pantheon.io/about/careers/detail?gh_jid=8202241'}
  ];
  const original=globalThis.fetch;
  try{
    for(const sample of cases){
      const payload={jobs:[{id:sample.id,title:'WordPress Engineer',
        location:{name:'Remote'},absolute_url:sample.url}]};
      globalThis.fetch=async()=>({ok:true,headers:{get:()=>null},
        text:async()=>JSON.stringify(payload)});
      const result=await publicJobs(sample,{maxJobs:1000,maxBytes:6_000_000});
      assert.equal(result.length,1);
      assert.equal(result[0].identity,
        'greenhouse:'+sample.account+':'+sample.id);
      payload.jobs[0].absolute_url='https://evil.invalid/role?gh_jid='+sample.id;
      await assert.rejects(()=>publicJobs(sample,{maxJobs:1000,maxBytes:6_000_000}),
        /Unexpected ATS job host/);
    }
  }finally{globalThis.fetch=original;}
});
