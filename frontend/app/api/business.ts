import { backendUrl, sessionToken, sessionCookie } from '../backend-auth';
import { json } from './security';
const messages: Record<number, string> = {
  401: '로그인이 만료되었습니다. 다시 로그인해 주세요.',
  403: '이 상담에 접근할 수 없습니다.',
  404: '학원 또는 상담을 찾을 수 없습니다.',
  409: '같은 요청 번호로 다른 내용을 제출할 수 없습니다. 내용을 확인해 주세요.',
  422: '입력한 학원, 학생 정보와 질문을 확인해 주세요.',
  429: '요청이 많습니다. 잠시 후 다시 시도해 주세요.',
};
export async function businessRequest(request: Request, path: string, body?: unknown, key?: string) {
  try {
    const base = backendUrl();
    if (!base) return json({ message: '상담 서비스 연결을 준비하고 있습니다.' }, 503);
    const isPublic = path === '/api/options' || path === '/api/academies';
    const token = isPublic ? undefined : await sessionToken();
    if (!isPublic && !token) return json({ message: messages[401] }, 401);
    const upstream = await fetch(base + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(key ? { 'Idempotency-Key': key } : {}) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: AbortSignal.timeout(10000), redirect: 'manual',
    });
    if (!upstream.ok) {
      const status = messages[upstream.status] ? upstream.status : 502;
      const failure = await upstream.json().catch(() => ({}));
      const realTestMessage = '실통화 시험은 서버 설정과 지정 시험 계정 확인 후 접수할 수 있습니다.';
      const message = status === 409 && failure && typeof failure === 'object' &&
        'detail' in failure && failure.detail === realTestMessage ? realTestMessage : messages[status];
      const response = json({ message: message || '상담 서비스에 연결할 수 없습니다. 다시 시도해 주세요.' }, status);
      if (status === 401) response.headers.set('Set-Cookie', sessionCookie(request));
      return response;
    }
    return json(await upstream.json(), upstream.status);
  } catch { return json({ message: '상담 서비스에 연결할 수 없습니다. 다시 시도해 주세요.' }, 502); }
}
