export function writable(request: Request) {
  const expectedOrigin = new URL(process.env.FRONTEND_ORIGIN || request.url).origin;
  return request.headers.get('origin') === expectedOrigin &&
    request.headers.get('content-type')?.split(';')[0] === 'application/json';
}
export function json(data: unknown, status=200) {
  return Response.json(data, { status, headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
}
