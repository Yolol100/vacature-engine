import test from 'node:test';
import assert from 'node:assert/strict';
import {
  PILOT_SOURCES,canonicalUrl,strongRoleKeys,isValidJob,normalizeJobs,
  buildRegisterIndex,matchRegister,sourceActive,cooldownMinutes,preliminaryInterest
} from '../src/logic.mjs';
const tenants=[PILOT_SOURCES[0],PILOT_SOURCES[1],PILOT_SOURCES[2]];
const urls=[
  x=>'https://job-boards.greenhouse.io/'+x.account+'/jobs/123',
  x=>'https://jobs.lever.co/'+x.account+'/123',
  x=>'https://jobs.ashbyhq.com/'+x.account+'/123'
];
const variants=['','?utm_source=linkedin','?utm_medium=social','?utm_campaign=remote','#apply','?ref=jobs','?mc_cid=xyz'];

test('strong job keys survive 21 harmless URL variants for all three official ATS providers',()=>{
  for(let i=0;i<tenants.length;i++){
    const first=strongRoleKeys(urls[i](tenants[i]));
    assert.ok(first.some(k=>k.startsWith('ats:')),tenants[i].source_id);
    for(const suffix of variants){
      const identity=strongRoleKeys(urls[i](tenants[i])+suffix);
      assert.deepEqual(identity.filter(k=>k.startsWith('ats:')),first.filter(k=>k.startsWith('ats:')));
    }
  }
});

test('100 cross-tenant URLs cannot pass official-host validation',()=>{
  for(let i=0;i<100;i++){
    const n=i.toString(36),source=tenants[i%3];
    const spoof=source.source_id==='greenhouse'
      ?{id:String(i),title:'WordPress Developer',absolute_url:'https://job-boards.greenhouse.io/unrelated'+n+'/jobs/'+i}
      :source.source_id==='lever'
      ?{id:String(i),text:'WordPress Developer',hostedUrl:'https://jobs.lever.co/unrelated'+n+'/'+i}
      :{title:'Web Developer',jobUrl:'https://jobs.ashbyhq.com/unrelated'+n+'/'+i,isListed:true};
    const normalized=normalizeJobs(source,source.source_id==='lever'?[spoof]:{jobs:[spoof]});
    assert.equal(normalized.length,1);
    assert.equal(isValidJob(normalized[0]),false);
  }
});

test('100 role URLs never incorrectly match distinct provider IDs',()=>{
  const fixture=[
    ['vacancy_id','status','','','','','canonical_url','official_url'],
    ['known','shown','','','','','https://jobs.lever.co/kinsta/role-1','']
  ];
  const known=buildRegisterIndex(fixture,[['vacancy_id','prepared_at','status','application_route','application_url']],[
    ['event_id','vacancy_id','occurred_at','event_type','source','status_after']
  ]);
  for(let i=2;i<=101;i++){
    const url='https://jobs.lever.co/kinsta/role-'+i;
    assert.deepEqual(matchRegister({url,source_url:url,identity:'lever:kinsta:role-'+i,source_id:'lever',source_job_id:'role-'+i},known),{known:false,applied:false});
  }
});

test('retired or blocked source and employer combinations cannot become active',()=>{
  for(const provider of ['retired','blocked','consolidated','inactive','']){
    const row=[['source_id'],['lever',...Array(11).fill(''),provider],['company-kinsta',...Array(11).fill(''),'active']];
    assert.equal(sourceActive(row,PILOT_SOURCES[1]),false);
    row[1][12]='active';row[2][12]=provider;
    assert.equal(sourceActive(row,PILOT_SOURCES[1]),false);
  }
});

test('cooldown grows monotonically and honors rate-limit hints',()=>{
  let prev=0;
  for(let failures=1;failures<=9;failures++){
    const result=cooldownMinutes(failures,503,undefined);
    assert.ok(result>=prev);
    prev=result;
  }
  for(const seconds of [60,1800,86400,172800,604800]){
    assert.ok(cooldownMinutes(1,429,seconds)>=Math.ceil(seconds/60));
  }
});

test('title selection distinguishes technical candidates from unrelated general roles',()=>{
  const positive=['WordPress Developer','Web Designer','Web Developer','Senior PHP Engineer',
    'React Frontend Engineer','WooCommerce developer','Elementor Builder','Full Stack Developer',
    'AI Workflow Automation Engineer','n8n Specialist','UX Designer','UI Designer','Design Systems Engineer','Core Web Vitals Specialist',
    'Experienced Software Engineer','Engineer, Applied AI','Senior Product Designer'];
  const negative=['VP Sales','Recruiting Manager','Executive Assistant','Accountant','Payroll Administrator','General Counsel'];
  for(const title of positive)assert.equal(preliminaryInterest({title,remote:'',location:''}),true,title);
  for(const title of negative)assert.equal(preliminaryInterest({title,remote:'',location:''}),false,title);
});
