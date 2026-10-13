import { currentIdentity, backendUrl, sessionCookie } from '../../backend-auth';
import { getDb } from '../../../db';
import { members } from '../../../db/schema';
import { eq } from 'drizzle-orm';
import { json, writable } from '../security';
export const dynamic = 'force-dynamic';
export async function GET(request: Request) {
  try {
  const mode = backendUrl() ? 'backend' : 'sites';
  const user = await currentIdentity();
  if (mode === 'backend') {
    const response = json({ mode, user: user ? {displayName:user.displayName,registered:true} : null }, user ? 200 : 401);
    if (!user) response.headers.set('Set-Cookie', sessionCookie(request));
    return response;
  }
  if (!user) return json({ mode, user:null },401);
  const [member] = await getDb().select().from(members).where(eq(members.userId,user.userId));
  return json({mode,user:{email:user.email,displayName:member?.nickname??user.displayName,registered:!!member}});
  } catch { return json({message:'계정 서비스에 연결할 수 없어요.'},502); }
}
export async function POST(request: Request) {
  if (backendUrl()) return json({message:'회원가입 화면을 이용해 주세요.'},400);
  const user = await currentIdentity();
  if (!user) return json({message:'로그인이 필요합니다.'},401);
  if (!writable(request)) return json({message:'요청을 확인해 주세요.'},403);
  let body: Record<string, unknown>;
  try {const input=await request.json();if(!input||typeof input!=='object'||Array.isArray(input))return json({message:'입력 내용을 확인해 주세요.'},400);body=input as Record<string, unknown>;}catch{return json({message:'입력 내용을 확인해 주세요.'},400);}
  const nickname=typeof body?.nickname==='string'?body.nickname.trim():'';
  if(nickname.length<2||nickname.length>24||/[\x00-\x1f]/.test(nickname))return json({message:'닉네임은 2~24자로 입력해 주세요.'},422);
  const db=getDb();
  const result=await db.insert(members).values({userId:user.userId,nickname,createdAt:new Date().toISOString()}).onConflictDoNothing().returning();
  if(!result.length)return json({message:'이미 가입된 계정입니다.'},409);
  return json({user:{email:user.email,displayName:nickname,registered:true}},201);
}
