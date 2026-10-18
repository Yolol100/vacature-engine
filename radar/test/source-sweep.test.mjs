import test from 'node:test';
import assert from 'node:assert/strict';
import {safeSourceUrl,activeRegistry,inspectSource,auditAll} from '../src/source-sweep.mjs';
test('public source URLs reject private addresses, credentials and downgrade',()=>{
 for(const url of ['http://example.com','https://localhost/a','https://127.0.0.1','https://192.168.0.1','https://user:pw@example.com','https://example.internal/','ftp://example.com'])assert.equal(safeSourceUrl(url),null);
 assert.equal(safeSourceUrl('https://example.org/jobs#temp'),'https://example.org/jobs');
});
test('registry scan selects every active row and skips retired',()=>{
 const header=['source_id','source_name','source_type','base_url','priority','access_mode','','','','','','','status'];
 const r=[header,['a','Employer','employer_direct','https://example.org','high','public_web','','','','','','','active'],['b','Retired','job_board','https://example.net','medium','public_web','','','','','','','retired']];
 assert.equal(activeRegistry(r).length,1);
 assert.throws(()=>activeRegistry([header,r[1],r[1]]),/duplicate/);
});
test('all active sources attempted, failures do not become vacancy results',async()=>{
 const samples=Array.from({length:219},(_,i)=>({id:'id'+i,type:'job_board',url:'https://example.org'}));
 const x=await auditAll(samples,{concurrency:8,inspect:async(s)=>({source_id:s.id,status:'access_limited',job_count:null})});
 assert.equal(x.length,219);
 assert.equal(new Set(x.map(x=>x.source_id)).size,219);
 assert.ok(x.every(x=>x.job_count===null));
});
test('a 200 OK is merely reachability, never job enumeration',async()=>{
 const x=await inspectSource({id:'demo',type:'employer_direct',url:'https://example.org'}, {request:async()=>({status:200,body:{cancel:async()=>{}}})});
 assert.equal(x.status,'public_surface_reachable_not_vacancies_verified');
 assert.equal(x.job_count,null);
});
