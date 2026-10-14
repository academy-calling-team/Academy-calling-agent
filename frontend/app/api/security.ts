export function writable(request: Request) {
  return request.headers.get('origin') === new URL(request.url).origin &&
    request.headers.get('content-type')?.split(';')[0] === 'application/json';
}
export function json(data: unknown, status=200) {
  return Response.json(data, { status, headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
}
