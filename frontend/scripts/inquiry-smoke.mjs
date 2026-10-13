import assert from 'node:assert/strict';
import {answerView,fieldLabel,inquiryPayload,submissionKey} from '../public/inquiry-model.js';
assert.equal(answerView({answered:false,yes_no:false,reason:'refused'}).kind,'unknown');
assert.equal(answerView({answered:true,yes_no:false}).kind,'no');
assert.equal(answerView({answered:true,yes_no:true}).kind,'yes');
assert.equal(answerView({answered:true,question_code:'class_time',yes_no:null}).kind,'time');
for(const reason of ['unknown','refused','not_asked'])assert.ok(answerView({answered:false,reason}).reason);
assert.equal(fieldLabel('grade','M2'),'중학교 2학년');assert.equal(fieldLabel('subject','MATH'),'수학');assert.equal(fieldLabel('level','MID'),'중급');
const base=process.env.FRONTEND_TEST_URL||'http://127.0.0.1:4173',backend=process.env.BACKEND_TEST_URL||'http://127.0.0.1:18770';
for(const url of [base,backend])assert.ok(['localhost','127.0.0.1'].includes(new URL(url).hostname),'Use isolated local test servers only.');
async function call(path,{body,cookie,key}={}){const r=await fetch(base+path,{method:body===undefined?'GET':'POST',headers:{...(body===undefined?{}:{'Content-Type':'application/json',Origin:base}),...(cookie?{Cookie:cookie}:{}),...(key?{'Idempotency-Key':key}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});return {status:r.status,data:await r.json(),cookie:r.headers.get('set-cookie')};}
async function account(){const body={login_name:'inq_'+crypto.randomUUID().replaceAll('-','').slice(0,12),password:'Synthetic_Inquiry_Pass123!'};assert.equal((await call('/api/auth/register',{body})).status,201);const login=await call('/api/auth/login',{body});assert.equal(login.status,200);return login.cookie.split(';')[0];}
const options=await call('/api/options');assert.equal(options.status,200);assert.ok(options.data.regions.includes('대구 북구 태전동'));
const academies=await call('/api/academies');assert.equal(academies.status,200);const school=academies.data.find(a=>a.academy_id==='demo-academy');assert.ok(school,'Seed the isolated test academy');
assert.equal((await call('/api/inquiries')).status,401);
const cookie=await account(),otherCookie=await account();
const payload=inquiryPayload({academy_id:school.academy_id,grade:'M2',subject:'MATH',level:'MID',region:school.region,question_codes:Object.keys(options.data.question_codes)});
const attempt=submissionKey(null,payload);assert.equal(submissionKey(attempt,payload).key,attempt.key);assert.notEqual(submissionKey(attempt,{...payload,academy_id:'changed'}).key,attempt.key);
assert.equal((await call('/api/inquiries',{body:payload,cookie})).status,422);
assert.equal((await call('/api/inquiries',{body:{...payload,student:{...payload.student,grade:'中2'}},cookie,key:crypto.randomUUID()})).status,422);
const created=await call('/api/inquiries',{body:{...payload,inquirer_id:'forged'},cookie,key:attempt.key});assert.equal(created.status,201);assert.equal(created.data.status,'queued');
const id=created.data.inquiry_id;
const duplicate=await call('/api/inquiries',{body:payload,cookie,key:attempt.key});assert.equal(duplicate.data.inquiry_id,id);assert.equal(duplicate.data.duplicate,true);
assert.equal((await call('/api/inquiries',{body:{...payload,student:{...payload.student,level:'HIGH'}},cookie,key:attempt.key})).status,409);
assert.equal((await call('/api/inquiries?limit=0', {cookie})).status,422);
assert.equal((await call('/api/inquiries',{cookie:otherCookie})).data.length,0);
assert.equal((await call('/api/inquiries/'+id,{cookie:otherCookie})).status,404);
const detail=(await call('/api/inquiries/'+id,{cookie})).data;assert.equal(detail.academy.name,school.name);assert.equal(detail.student.grade,'M2');
// This key belongs only to the temporary SQLite test server, not a real environment.
async function internal(path,body={}){const r=await fetch(backend+path,{method:'POST',headers:{'Content-Type':'application/json','X-Internal-Key':'synthetic-inquiry-check-only'},body:JSON.stringify(body)});assert.equal(r.status,200,await r.clone().text());return r.json();}
await internal('/internal/mock/tick');const calling=(await call('/api/inquiries/'+id,{cookie})).data;assert.equal(calling.status,'calling');const cid=calling.attempts[0].call_id;
const answers=calling.questions.map((q,i)=>({...q,asked:i!==4,answered:[0,1,5].includes(i),yes_no:i===0?true:i===1?false:null,reason:i===2?'unknown':i===3?'refused':i===4?'not_asked':null,detail:i===5?'화목 19:00':i===1?'픽업 불가':i===0?'운행 가능':'추가 확인 필요'}));
await internal('/internal/calls/'+cid+'/result',{result_id:'result_'+cid,outcome:'answered',disclosure_played:true,consult_accepted:true,available_times:['평일 14:00'],answers,unresolved:answers.filter(a=>!a.answered).map(a=>a.question_id),summary_text:'합성 검증 결과',notes:'격리 테스트',latency:null,duration_sec:0,transcript:[]});
const completed=(await call('/api/inquiries/'+id,{cookie})).data;assert.equal(completed.status,'completed');assert.deepEqual(completed.result.answers.map(a=>answerView(a).kind),['yes','no','unknown','unknown','unknown','time']);assert.ok(!('transcript' in completed.result));
async function createNext(){return (await call('/api/inquiries',{body:payload,cookie,key:crypto.randomUUID()})).data.inquiry_id;}
const retryId=await createNext();await internal('/internal/mock/tick');const retry=(await call('/api/inquiries/'+retryId,{cookie})).data;assert.equal(retry.status,'calling');await internal('/internal/calls/'+retry.attempts[0].call_id+'/events',{event_id:crypto.randomUUID(),type:'busy',occurred_at:new Date().toISOString()});assert.equal((await call('/api/inquiries/'+retryId,{cookie})).data.status,'retry_wait');
const failId=await createNext();await internal('/internal/mock/tick');const fail=(await call('/api/inquiries/'+failId,{cookie})).data;assert.equal(fail.status,'calling');await internal('/internal/calls/'+fail.attempts[0].call_id+'/events',{event_id:crypto.randomUUID(),type:'invalid_number',occurred_at:new Date().toISOString()});const failed=(await call('/api/inquiries/'+failId,{cookie})).data;assert.equal(failed.status,'failed');assert.equal(failed.failure_reason,'invalid_number');
assert.equal((await call('/api/inquiries?limit=1&offset=0',{cookie})).data.length,1);assert.equal((await call('/api/inquiries?limit=1&offset=1',{cookie})).data.length,1);
await call('/api/auth/logout',{body:{},cookie});assert.equal((await call('/api/inquiries/'+id,{cookie})).status,401);await call('/api/auth/logout',{body:{},cookie:otherCookie});
console.log('PASS: backend options/academies, encoded submission, stable idempotency/conflict, ownership, pagination, queued/calling/retry_wait/completed/failed, answer reasons and logout.');
