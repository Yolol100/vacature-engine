import test from 'node:test';
import assert from 'node:assert/strict';
import {extractPublicRoleClues,inspectSource} from '../src/source-sweep.mjs';
import {mergeCoverage,selectDiscoveryRows,selectPublicClueRows,submittedApplicationUrls} from '../src/drive-scan-sync.mjs';

const run='39155142052',now=new Date().toISOString();
const coverHead=['bron_id','bronnaam','brontype','prioriteit','registratiestatus','bron_url','controlekanaal','laatst_bezocht_utc','resultaat','bewijs_url','laatste_run_id','opmerkingen'];
const register=[
  ['source_id','source_name','source_type','base_url','priority','access_mode',
    '','','','','','','status'],
  ['company-test','Example','employer_direct','https://example.org/careers',
    'high','public_web','','','','','','','active'],
  ['retired','Legacy','job_board','https://old.example.org/jobs',
    'low','public_web','','','','','','','retired']
];
const coverage=[
  coverHead,
  ['company-test','Example','employer_direct','high','active',
    'https://example.org/careers','chatgpt_web_discovery','','nog_niet_bewezen','','','note'],
  ['retired','Legacy','job_board','low','retired',
    'https://old.example.org/jobs','niet_actief','','niet_actief','','','note']
];
function sweep(){
  return {schema_version:1,mode:'public_surface_audit_not_vacancy_enumeration',
    run_id:run,registered_active:1,attempted:1,official_job_matches_verified:0,
    source_statuses:[{source_id:'company-test',status:'public_surface_reachable_not_vacancies_verified',
      checked_at:now,evidence_url:'https://example.org/careers',http_status:200,job_count:null}]};
}
const published='<script type="application/ld+json">'+
  JSON.stringify({'@context':'https://schema.org','@type':'JobPosting',
    title:'WordPress Developer',url:'https://example.org/careers/wordpress-developer',
    datePosted:'2026-10-18'})+'</script>';
test('bounded public JSON-LD extraction keeps date as unverified hint',()=>{
  const clues=extractPublicRoleClues('<html>'+published+'</html>','https://example.org/careers');
  assert.equal(clues.length,1);
  assert.equal(clues[0].method,'json_ld_jobposting');
  assert.equal(clues[0].source_date_hint,'2026-10-18');
});
test('only same employer host and exact job-like paths are accepted',()=>{
  const page='<a href="https://other.example/jobs/wordpress-dev">WordPress Developer</a>'+
    '<a href="/about">WordPress Developer</a>'+
    '<a href="/careers/wordpress-dev">WordPress Developer</a>';
  const matches=extractPublicRoleClues(page,'https://example.org/careers');
  assert.equal(matches.length,1);
  assert.equal(matches[0].url,'https://example.org/careers/wordpress-dev');
  assert.deepEqual(extractPublicRoleClues('a'.repeat(384001),'https://example.org/careers'),[]);
});
test('successful public response with job clues is still NOT a verified vacancy',async()=>{
  const page='<html>'+published+'</html>';
  const res=await inspectSource({id:'company-test',type:'employer_direct',
    url:'https://example.org/careers'},{
    request:async()=>({status:200,headers:{get:()=> 'text/html'},
      text:async()=>page})
  });
  assert.equal(res.status,'public_vacancy_link_discovery_unverified');
  assert.equal(res.job_count,null);
  assert.equal(res.jobposting_discoveries.length,1);
});
test('complete active source IDs merge without touching historical inactive evidence',()=>{
  const updated=mergeCoverage(register,coverage,sweep(),run);
  assert.equal(updated.length,2);
  assert.equal(updated[0][2],'https://example.org/careers');
  assert.equal(updated[0][3],run);
  assert.deepEqual(updated[1],['','niet_actief','','']);
  const tampered=structuredClone(coverage);
  tampered[1][1]='Wrong';
  assert.throws(()=>mergeCoverage(register,tampered,sweep(),run),/scan_coverage_register_drift/);
  const missing=structuredClone(sweep());
  missing.source_statuses[0].source_id='other';
  assert.throws(()=>mergeCoverage(register,coverage,missing,run),/scan_status_invalid/);
});
test('feed candidate stores only unverified deduplicated lead, never a definitive official role',()=>{
  const d={schema_version:1,mode:'read_only_discovery_only',github_run_id:run,
    application_submissions:0,google_sheet_rows_written:0,candidates:[{
      observation_key:'himalayas:global:0123456789abcdef01234567',
      source_id:'himalayas',title:'WordPress Developer',employer:'Example',
      discovery_url:'https://himalayas.app/jobs/wordpress-developer',
      source_url:'https://himalayas.app/jobs'
    }]};
  const items=selectDiscoveryRows(d,{ids:[],urls:[]},now,run);
  assert.equal(items.length,1);
  assert.match(items[0][9],/onbevestigde/);
  assert.equal(items[0][7],'');
  assert.equal(selectDiscoveryRows(d,{ids:[],urls:[items[0][5]]},now,run).length,0);
  assert.throws(()=>selectDiscoveryRows({...d,application_submissions:1},{ids:[],urls:[]},now,run),/discovery_receipt_invalid/);
});
test('public clues reuse prior IDs and tracked role URLs with no duplicate writes',()=>{
  const s=sweep();
  s.source_statuses[0].status='public_vacancy_link_discovery_unverified';
  s.source_statuses[0].jobposting_discoveries=extractPublicRoleClues(
    '<html>'+published+'</html>','https://example.org/careers');
  const rows=selectPublicClueRows(s,{ids:[],urls:[]},now,run);
  assert.equal(rows.length,1);
  assert.equal(rows[0][9],'onbevestigde_bronvondst');
  assert.equal(rows[0][7],'2026-10-18');
  assert.equal(selectPublicClueRows(s,{ids:[],urls:[rows[0][5]+'?utm_source=scan']},now,run).length,0);
  s.source_statuses[0].jobposting_discoveries[0].url='https://untrusted.invalid/jobs/wordpress';
  assert.throws(()=>selectPublicClueRows(s,{ids:[],urls:[]},now,run),/public_clue_invalid/);
});

test('live submitted and applied Application URLs exclude discovery, but drafts do not',()=>{
  const url='https://himalayas.app/jobs/wordpress-developer';
  const statuses=[['status'],['drafted'],['submitted'],['applied'],['prepared_cv_ready']];
  const urls=[['application_url'],[url],[url+'?utm_source=application'],
    ['https://jobs.ashbyhq.com/company/role-id'],['https://other.example.org/new']];
  const applied=submittedApplicationUrls(statuses,urls);
  assert.equal(applied.length,2);
  assert.equal(applied.includes(url),false);
  const d={schema_version:1,mode:'read_only_discovery_only',github_run_id:run,
    application_submissions:0,google_sheet_rows_written:0,candidates:[{
      observation_key:'himalayas:global:0123456789abcdef01234567',source_id:'himalayas',
      title:'WordPress Developer',discovery_url:url,source_url:'https://himalayas.app/jobs'
    }]};
  assert.equal(selectDiscoveryRows(d,{ids:[],urls:applied},now,run).length,0);
  assert.throws(()=>submittedApplicationUrls([['not_status']],urls),/scan_application_history_schema/);
});

test('generic board landing pages and irrelevant WordPress skill tags are not vacancies',()=>{
  const base='https://example.org/careers';
  const html='<a href="/careers">WordPress jobs</a>'+
    '<a href="/jobs/wordpress">WordPress jobs</a>'+
    '<a href="/jobs/graphic-designer">Graphic Designer WordPress Canva</a>'+
    '<a href="/jobs/wordpress-content-writer">WordPress Content Writer</a>'+
    '<a href="/jobs/wordpress-web-developer">WordPress Web Developer</a>';
  const clues=extractPublicRoleClues(html,base);
  assert.equal(clues.length,1);
  assert.equal(clues[0].url,'https://example.org/jobs/wordpress-web-developer');
});
