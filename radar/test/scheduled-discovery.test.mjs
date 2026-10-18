import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {authorizeDiscovery,sourceIndex,seenKeys,runApprovedDiscovery}
  from '../src/scheduled-discovery.mjs';

const context=()=>({
  GITHUB_REPOSITORY:'Yolol100/vacature-engine',GITHUB_REF:'refs/heads/main',
  GITHUB_WORKFLOW:'Vacature Radar quarter-hour observations',
  GITHUB_EVENT_NAME:'schedule',GITHUB_ACTOR:'github-actions[bot]',
  GITHUB_RUN_ID:'39147000001',
  VACATURE_REGISTER_ID:'1Owg3s5ZzPuCYTucp6ArgUNoWijKDr2TwvgbAUsJWdz0',
  RADAR_RESULT_ID:'1uLr7snvnCw2JmzdIL_yN4Jln0tMZJnOZK-mfh_DygwQ',
  RADAR_DISCOVERY_SCOPE:'approved_feeds_readonly'
});
test('scheduled discovery allows genuine schedule and owner-only issue, no spoofed runs',()=>{
  assert.doesNotThrow(()=>authorizeDiscovery(context()));
  assert.doesNotThrow(()=>authorizeDiscovery({
    ...context(),GITHUB_EVENT_NAME:'issues',GITHUB_ACTOR:'Yolol100',
    RADAR_ISSUE_TITLE:'[radar] quarter 10'
  }));
  for(const bad of [
    {GITHUB_REPOSITORY:'other/repo'},
    {GITHUB_REF:'refs/heads/feature'},
    {GITHUB_EVENT_NAME:'pull_request'},
    {GITHUB_EVENT_NAME:'issues',GITHUB_ACTOR:'other'},
    {GITHUB_EVENT_NAME:'issues',GITHUB_ACTOR:'Yolol100',RADAR_ISSUE_TITLE:'unknown'},
    {RADAR_PERSIST:'1'},
    {RADAR_DISCOVERY_SCOPE:'unrestricted'},
    {RADAR_RESULT_ID:'unexpected'}
  ])assert.throws(()=>authorizeDiscovery({...context(),...bad}),/discovery_context_denied/);
});
test('source metadata and history remain read-only, bounded and validated',()=>{
  const source=[
    [['source_id'],['himalayas'],['remote-ok'],['irrelevant']],
    [['source_type'],['job_board'],['job_board'],['job_board']],
    [['priority'],['high'],['high'],['low']],
    [['status'],['active'],['active'],['retired']]
  ];
  const found=sourceIndex(source);
  assert.equal(found.active.length,2);
  assert.equal(found.map.get('irrelevant').status,'retired');
  assert.throws(()=>sourceIndex([source[0],source[1]]),/discovery_sources_schema/);
  const history=[
    [['observation_key'],['ashby:zapier:123']],
    [['officiele_url'],['https://jobs.ashbyhq.com/zapier/123']],
    [['identity'],['ashby:zapier:456']],
    [['official_url'],['https://jobs.ashbyhq.com/zapier/456']]
  ];
  assert.equal(seenKeys(history).ids.size,2);
  assert.ok(seenKeys(history).roles.has('ats:ashby:zapier:123'));
  assert.throws(()=>seenKeys([]),/discovery_history_schema/);
});
test('all eight active official approved API/RSS feed adapters checked, but leads never verified',async()=>{
  const specs=JSON.parse(readFileSync('../ingestion/source-specs.deploy.json','utf8'));
  const selected=specs.filter(x=>['remotive','jobicy-api','himalayas',
    'we-work-remotely','remote-ok','remote-landers-api',
    'remotejobs-org','arbeitnow-api'].includes(x.source_id));
  assert.equal(selected.length,8);
  const ids=['source_id'],types=['source_type'],priorities=['priority'],states=['status'];
  for(const spec of selected){
    ids.push(spec.source_id);types.push(spec.source_type);
    priorities.push(spec.source_id==='himalayas'?'high':'medium');
    states.push('active');
  }
  const config=[
    ['key','value'],['radar_enabled','FALSE'],['radar_delivery','none'],
    ['direct_discovery_order','employer_direct,ats,discovery_api,wordpress_discovery,google,job_board,discovery'],
    ['high_source_order','himalayas,remote-ok']
  ];
  const reg=[{values:[['vacancy_id','status']]},{values:[['canonical_url','official_url']]},
    {values:[['vacancy_id']]},{values:[['status']]},{values:[['application_url']]},
    {values:[['event_id','vacancy_id']]},{values:[['event_type']]},
    {values:[['status_after']]}];
  const radar=[{values:[['observation_key']]},{values:[['officiele_url']]},
    {values:[['identity']]},{values:[['official_url']]}];
  let calls=0;
  const result=await runApprovedDiscovery({
    env:context(),token:async()=> 'mock',
    read:async(id,names)=>{
      if(names.length===1)return[{values:config}];
      if(names.length===4&&names[0].includes('Bronnen'))return[
        {values:ids.map(x=>[x])},{values:types.map(x=>[x])},
        {values:priorities.map(x=>[x])},{values:states.map(x=>[x])}];
      if(names.length===8)return reg;
      if(names.length===4&&names[0].includes('Nieuwe vacatures'))return radar;
      throw Error('unexpected test range');
    },
    loadSpecs:()=>specs,
    fetchJobs:async source=>{
      calls++;
      if(source.source_id!=='himalayas')return [];
      return [{
        source_id:source.source_id,source_account:source.account,
        source_job_id:'a'.repeat(24),
        identity:source.source_id+':'+source.account+':'+'a'.repeat(24),
        title:'Remote WordPress Developer',
        employer:'Test employer',url:'https://himalayas.app/jobs/remote-wordpress-developer',
        source_url:'https://himalayas.app/jobs',location:'Remote Worldwide',remote:'remote'
      }];
    }
  });
  assert.equal(calls,8);
  assert.equal(result.registered_active_source_entries,8);
  assert.equal(result.checked_feeds.length,8);
  assert.equal(result.candidates.length,1);
  assert.match(result.candidates[0].verification,/discovery_only/);
  assert.equal(result.google_sheet_rows_written,0);
  assert.equal(result.application_submissions,0);
});
test('non-active or missing feeds remain explicitly skipped, never counted as checked',async()=>{
  const s=sourceIndex([[['source_id'],['himalayas']],[['source_type'],['job_board']],
    [['priority'],['high']],[['status'],['retired']]]);
  assert.equal(s.active.length,0);
});
