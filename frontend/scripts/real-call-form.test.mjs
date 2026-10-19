import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import {inquiryPayload,submissionKey} from '../public/inquiry-model.js';

const source=readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
function section(start,end){
 const a=source.indexOf(start),b=source.indexOf(end,a+start.length);
 assert.ok(a>=0&&b>a);return source.slice(a,b);
}
function fixture({mock=false,ready=true,confirmed=false}={}){
 const posts=[],button={},nodes={};
 const elements=Object.fromEntries(Object.entries({academy_id:'fixture-academy',grade:'M2',subject:'MATH',level:'MID',region:'대구 북구 침산동'}).map(([key,value])=>[key,{value}]));
 elements.real_test_confirm={checked:confirmed};
 const form={elements,querySelectorAll:()=>[{value:'shuttle'},{value:'pickup'},{value:'class_time'}],querySelector:()=>button};
 nodes['#form']=form;
 for(const id of ['#error','#school-summary','#count-summary','#real-test-notice','#real-test-message'])nodes[id]={textContent:''};
 const context={
  $:id=>nodes[id],head:()=>'',select:()=>'',esc:String,submitting:false,formValues:{},mockMode:false,
  catalog:{state:'ready',academies:[{academy_id:'fixture-academy',name:'시험용',region:'대구 북구 침산동',is_mock:mock,is_test:!mock,can_submit:ready,notice:ready?'실제 전화 1회':'시험 준비 중'}],options:{grade:['M2'],subject:['MATH'],level:['MID'],regions:['대구 북구 침산동'],question_codes:{shuttle:'통학 차량',pickup:'픽업',class_time:'수업 시간'}}},
  pending:null,user:{displayName:'fixture'},sessionEpoch:1,routeEpoch:1,tasks:[],location:{hash:''},
  inquiryPayload,submissionKey:(old,body)=>submissionKey(old,body,()=>'fixture-request'),
  sessionStorage:{setItem(){}},render(){},clearPending(){},toast(){},
  api:async(url,init)=>{posts.push({url,payload:JSON.parse(init.body)});return {inquiry_id:'synthetic-only',status:'queued'};},
 };
 vm.createContext(context);
 vm.runInContext(section('function form(){','function summary(){')+
  section('function summary(){','function answersHtml(')+
  section('function captureForm(){','async function loadCatalog(')+
  section('async function submitInquiry(','function mockBanner('),context);
 return {context,form,elements,nodes,button,posts,submit:()=>context.submitInquiry({preventDefault(){},target:form})};
}
test('Rendered form includes the real-call control consumed by submission',()=>{
 const f=fixture(),html=f.context.form();
 assert.match(html,/<input[^>]*name="real_test_confirm"/);
 assert.match(html,/id="real-test-notice"/);
 assert.doesNotMatch(html,/현재 연결된 개발 백엔드는 실제 전화를 발신하지 않습니다/);
 f.context.summary();assert.equal(f.elements.real_test_confirm.required,true);
 assert.equal(f.nodes['#real-test-notice'].hidden,false);
});
test('Unconfirmed real call stays local; confirmed real call submits once',async()=>{
 const f=fixture();await f.submit();assert.equal(f.posts.length,0);
 assert.match(f.nodes['#error'].textContent,/수신자 준비/);
 f.elements.real_test_confirm.checked=true;await f.submit();
 assert.equal(f.posts.length,1);assert.equal(f.context.location.hash,'detail/synthetic-only');
 assert.equal(f.posts[0].payload.academy_id,'fixture-academy');
 assert.deepEqual(f.posts[0].payload.question_codes,['shuttle','pickup','class_time']);
 assert.equal(Object.hasOwn(f.posts[0].payload,'real_test_confirm'),false);
});
test('Disabled real academy blocks the button and never submits',async()=>{
 const f=fixture({ready:false,confirmed:true});f.context.summary();
 assert.equal(f.button.disabled,true);await f.submit();assert.equal(f.posts.length,0);
});
test('Ordinary mock inquiry needs no real-call confirmation',async()=>{
 const f=fixture({mock:true});f.context.summary();
 assert.equal(f.nodes['#real-test-notice'].hidden,true);
 assert.equal(f.elements.real_test_confirm.required,false);
 await f.submit();assert.equal(f.posts.length,1);
});
