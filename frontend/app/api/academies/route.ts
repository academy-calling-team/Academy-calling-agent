import { businessRequest } from '../business';
export const dynamic = 'force-dynamic';
export async function GET(request: Request) { return businessRequest(request, '/api/academies'); }
