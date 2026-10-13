import { currentIdentity, backendUrl } from '../../backend-auth';
import { getDb } from '../../../db';
import { members, drafts } from '../../../db/schema';
import { eq, desc } from 'drizzle-orm';
import { json, writable } from '../security';
export const dynamic = 'force-dynamic';
async function identity(){const u=await currentIdentity();if(!u)return null;if(backendUrl())return u;const [m]=await getDb().select().from(members).where(eq(members.userId,u.userId));return m?u:null;}
export async function GET(){const u=await identity();if(!u)return json({message:'회원 가입 후 이용해 주세요.'},401);const rows=await getDb().select().from(drafts).where(eq(drafts.userId,u.userId)).orderBy(desc(drafts.createdAt));return json({tasks:rows.map(r=>JSON.parse(r.payload))});}
export async function POST(request:Request){const u=await identity();if(!u)return json({message:'회원 가입 후 이용해 주세요.'},401);if(!writable(request))return json({message:'요청을 확인해 주세요.'},403);let b: Record<string, unknown>;try{const input=await request.json();if(!input||typeof input!=='object'||Array.isArray(input))return json({message:'입력 내용을 확인해 주세요.'},400);b=input as Record<string, unknown>;}catch{return json({message:'입력 내용을 확인해 주세요.'},400);}
const codes=['shuttle','pickup','level_fit','vacancy','level_test','class_time'];
const grades=['초등학교 1학년','초등학교 2학년','초등학교 3학년','초등학교 4학년','초등학교 5학년','초등학교 6학년','중학교 1학년','중학교 2학년','중학교 3학년','고등학교 1학년','고등학교 2학년','고등학교 3학년'];
if(typeof b.school!=='number'||!Number.isInteger(b.school)||b.school<0||b.school>2||!grades.includes(b.grade as string)||!['수학','영어','국어','과학','사회'].includes(b.subject as string)||!['중급','상급','기초'].includes(b.level as string)||!['대구 북구 침산동','대구 수성구'].includes(b.region as string)||!Array.isArray(b.codes)||b.codes.length<1||b.codes.length>6||new Set(b.codes).size!==b.codes.length||b.codes.some((c:unknown)=>!codes.includes(c as string)))return json({message:'입력 내용을 확인해 주세요.'},422);
const task={id:'q'+crypto.randomUUID(),school:b.school,grade:b.grade,subject:b.subject,level:b.level,region:b.region,codes:b.codes,status:'draft',date:new Date().toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})};
if(backendUrl())await getDb().insert(members).values({userId:u.userId,nickname:u.displayName,createdAt:new Date().toISOString()}).onConflictDoNothing();
await getDb().insert(drafts).values({id:task.id,userId:u.userId,payload:JSON.stringify(task),createdAt:new Date().toISOString()});return json({task},201);}
