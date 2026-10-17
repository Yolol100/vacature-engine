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
  const {sources,unsupported}=selectSupportedSources(manifest);
  assert.equal(sources.length,8);
  assert.equal(unsupported.length,3);
  assert.deepEqual(sources.map(s=>s.source_id+':'+s.account),[
    'greenhouse:automatticcareers','lever:kinsta','lever:siteground',
    'greenhouse:acquia','greenhouse:gitlab','greenhouse:digitalocean98',
    'greenhouse:pantheon','ashby:zapier'
  ]);
  assert.ok(sources.every(s=>s.employer_source_id.startsWith('company-')));
  assert.deepEqual(unsupported,['personio','workable','workable']);
});

test('invalid tenant, adapter drift, missing owner registration and duplicate sources fail closed',()=>{
  const invalid=[
    [{...sample,account:'https://evil.invalid'}],
    [{...sample,options:{}}],
    [{...sample,adapter:'lever'}],
    [{...sample,source_type:'discovery'}],
    [sample,{...sample}],
    [],
    Array.from({length:101},()=>sample)
  ];
  for(const specs of invalid)
    assert.throws(()=>selectSupportedSources(specs),/radar source/);
});

test('nonimplemented adapters never turn into an invented technical provider',()=>{
  const result=selectSupportedSources([sample,{
    source_id:'workable',adapter:'workable',source_type:'ats',
    account:'humanmade',employer:'Human Made'}]);
  assert.equal(result.sources.length,1);
  assert.deepEqual(result.unsupported,['workable']);
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
