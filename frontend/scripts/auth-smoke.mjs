import assert from 'node:assert/strict';
const origin='http://127.0.0.1:4173';
const anon=await fetch(origin+'/api/drafts');assert.equal(anon.status,401);
const login=await fetch(origin+'/signin-with-chatgpt?return_to=/',{redirect:'manual'});
const cookie=login.headers.getSetCookie().map(v=>v.split(';')[0]).join('; ');assert.ok(cookie);
const account=await fetch(origin+'/api/account',{headers:{cookie}});assert.equal(account.status,200);assert.equal((await account.json()).user.registered,true);
async function post(path,body,source=origin){return fetch(origin+path,{method:'POST',headers:{cookie,Origin:source,'Content-Type':'application/json'},body:JSON.stringify(body)});}
assert.equal((await post('/api/account',{nickname:'Duplicate'})).status,409);
assert.equal((await post('/api/account',{nickname:'Cross Site'},'https://other.example')).status,403);
assert.equal((await post('/api/drafts',{school:0,codes:[]})).status,422);
const saved=await post('/api/drafts',{school:0,grade:'중학교 2학년',subject:'수학',level:'중급',region:'대구 북구 침산동',codes:['shuttle','class_time'],userId:'local_other'});
assert.equal(saved.status,201);const created=(await saved.json()).task;
const own=await fetch(origin+'/api/drafts',{headers:{cookie}});const rows=(await own.json()).tasks;assert.ok(rows.some(t=>t.id===created.id));assert.ok(!rows.some(t=>t.id==='other_private_draft'));
const forgedQuery=await fetch(origin+'/api/drafts?userId=local_other',{headers:{cookie}});assert.ok(!(await forgedQuery.json()).tasks.some(t=>t.id==='other_private_draft'));
console.log('PASS: anonymous rejection, authenticated account, duplicate signup, CSRF, input validation, server-owned draft, owner isolation, forged owner ignored.');
