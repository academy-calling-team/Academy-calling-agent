import { currentIdentity, backendUrl } from '../../backend-auth';
import { businessRequest } from '../business';
import { json, writable } from '../security';
export const dynamic = 'force-dynamic';
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const limit = params.get('limit') ?? '10', offset = params.get('offset') ?? '0';
  if (!/^\d+$/.test(limit) || +limit < 1 || +limit > 100 || !/^\d+$/.test(offset) || !Number.isSafeInteger(+offset))
    return json({ message: '조회 범위를 확인해 주세요.' }, 422);
  return businessRequest(request, `/api/inquiries?limit=${+limit}&offset=${+offset}`);
}
export async function POST(request: Request) {
  if (!writable(request)) return json({ message: '요청을 확인해 주세요.' }, 403);
  const key = request.headers.get('Idempotency-Key');
  if (!key || !/^[A-Za-z0-9_-]{1,80}$/.test(key)) return json({ message: '요청 번호를 확인해 주세요.' }, 422);
  try {
    if (!backendUrl()) return json({ message: '상담 서비스 연결을 준비하고 있습니다.' }, 503);
    const user = await currentIdentity();
    if (!user) return json({ message: '로그인이 필요합니다.' }, 401);
    const body = await request.json() as Record<string, unknown>;
    if (!body || typeof body !== 'object' || Array.isArray(body)) return json({ message: '입력 내용을 확인해 주세요.' }, 400);
    // The backend owner is always obtained from /auth/me, never the submitted owner.
    return businessRequest(request, '/api/inquiries', {
      inquirer_id: user.userId.slice('backend:'.length),
      academy_id: body.academy_id, student: body.student, question_codes: body.question_codes,
    }, key);
  } catch (error) { return json({ message: error instanceof SyntaxError ? '입력 내용을 확인해 주세요.' : '상담 서비스에 연결할 수 없습니다.' }, error instanceof SyntaxError ? 400 : 502); }
}
