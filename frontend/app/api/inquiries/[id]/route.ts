import { businessRequest } from '../../business';
import { json } from '../../security';
export const dynamic = 'force-dynamic';
export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!/^[A-Za-z0-9_-]{1,36}$/.test(id)) return json({ message: '상담 번호를 확인해 주세요.' }, 404);
  return businessRequest(request, `/api/inquiries/${encodeURIComponent(id)}`);
}
