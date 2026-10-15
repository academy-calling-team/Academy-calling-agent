import { json } from '../security';
// Consultation screens use /api/inquiries. Legacy D1 drafts are preserved separately.
export const dynamic = 'force-dynamic';
export async function GET() { return json({ message: '임시 저장 기능은 현재 사용할 수 없습니다.' }, 503); }
export async function POST() { return json({ message: '임시 저장 기능은 현재 사용할 수 없습니다.' }, 503); }
