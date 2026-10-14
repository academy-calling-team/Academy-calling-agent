import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export async function GET() {
  const shell = await readFile(join(process.cwd(), 'app', 'shell.html'), 'utf8');
  return new Response(shell, { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
}
