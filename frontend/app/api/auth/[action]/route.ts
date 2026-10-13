import { backendUrl, backendRequest, sessionToken, sessionCookie } from '../../../backend-auth';
import { json, writable } from '../../security';
export const dynamic = 'force-dynamic';
const messages: Record<number, string> = {
  401: '아이디 또는 비밀번호를 확인해 주세요.', 409: '이미 사용 중인 아이디입니다.',
  422: '아이디는 영문 소문자로 시작하는 3~32자, 비밀번호는 12~128자로 입력해 주세요.',
  429: '로그인이 일시적으로 잠겼어요. 5분 후 다시 시도해 주세요.',
};
export async function POST(request: Request, context: { params: Promise<{ action: string }> }) {
  if (!writable(request)) return json({ message: '요청을 확인해 주세요.' }, 403);
  const { action } = await context.params;
  if (!['register', 'login', 'logout'].includes(action)) return json({ message: '잘못된 요청입니다.' }, 404);
  try {
    if (!backendUrl()) return json({ message: '계정 서비스를 사용할 수 없습니다.' }, 503);
    let body: { login_name: string; password: string } | undefined;
    if (action !== 'logout') {
      const input = await request.json() as Record<string, unknown>;
      if (!input || typeof input.login_name !== 'string' || typeof input.password !== 'string' ||
          !/^[a-z][a-z0-9_]{2,31}$/.test(input.login_name) || [...input.password].length < 12 || [...input.password].length > 128)
        return json({ message: messages[422] }, 422);
      body = { login_name: input.login_name, password: input.password };
    }
    const token = action === 'logout' ? await sessionToken() : undefined;
    if (action === 'logout' && !token) {
      const response = json({ logged_out: true });
      response.headers.set('Set-Cookie', sessionCookie(request)); return response;
    }
    const upstream = await backendRequest(`/auth/${action}` as '/auth/register' | '/auth/login' | '/auth/logout', body, token);
    // Already expired/revoked sessions are safely signed out too.
    if (action === 'logout' && (upstream.ok || upstream.status === 401)) {
      const response = json({ logged_out: true });
      response.headers.set('Set-Cookie', sessionCookie(request)); return response;
    }
    if (!upstream.ok) return json({ message: messages[upstream.status] || '계정 서비스에 연결할 수 없어요. 다시 시도해 주세요.' }, [401,409,422,429].includes(upstream.status) ? upstream.status : 502);
    if (action === 'register') return json({ registered: true, login_name: body!.login_name }, 201);
    const data = await upstream.json() as { access_token: string; expires_at: string };
    const duration = Math.floor((Date.parse(data.expires_at) - Date.now()) / 1000);
    if (!data.access_token || !Number.isFinite(duration) || duration <= 0) throw new Error('Invalid session');
    const response = json({ logged_in: true });
    response.headers.set('Set-Cookie', sessionCookie(request, data.access_token, Math.min(duration, 86400)));
    return response;
  } catch (error) {
    return json({ message: error instanceof SyntaxError ? '입력 내용을 확인해 주세요.' : '계정 서비스에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.' }, error instanceof SyntaxError ? 400 : 502);
  }
}
