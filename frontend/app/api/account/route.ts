import { currentIdentity, backendUrl, sessionCookie } from '../../backend-auth';
import { json } from '../security';
export const dynamic = 'force-dynamic';
export async function GET(request: Request) {
  if (!backendUrl()) return json({ message: '계정 서비스에 연결할 수 없어요.' }, 503);
  try {
    const user = await currentIdentity();
    const response = json({ mode: 'backend', user: user ? { displayName: user.displayName, registered: true } : null }, user ? 200 : 401);
    if (!user) response.headers.set('Set-Cookie', sessionCookie(request));
    return response;
  } catch { return json({ message: '계정 서비스에 연결할 수 없어요.' }, 502); }
}
export async function POST() { return json({ message: '회원가입 화면을 이용해 주세요.' }, 400); }
