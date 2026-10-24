/**
 * Same-origin API BFF — preserves the legacy /api contract:
 * cookie session, Origin checks, error messages, inquirer_id injection.
 */

export function backendUrl(): string | null {
  const value = process.env.ACADEMY_BACKEND_URL || process.env.VITE_ACADEMY_BACKEND_URL;
  if (typeof value !== 'string' || !value.trim()) return null;
  try {
    const url = new URL(value);
    if (
      !['http:', 'https:'].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    ) {
      return null;
    }
    return url.href.replace(/\/$/, '');
  } catch {
    return null;
  }
}

export const SESSION_COOKIE = 'hakwon_backend_session';

export function readCookie(header: string | undefined, name: string): string | null {
  if (!header) return null;
  for (const part of header.split(';')) {
    const [k, ...rest] = part.trim().split('=');
    if (k === name) return decodeURIComponent(rest.join('='));
  }
  return null;
}

export function sessionCookie(requestUrl: string, token = '', maxAge = 0): string {
  const secure = new URL(process.env.FRONTEND_ORIGIN || requestUrl).protocol === 'https:' ? '; Secure' : '';
  return `${SESSION_COOKIE}=${encodeURIComponent(token)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge}${secure}`;
}

function cookieHeader(request: Request): string | undefined {
  return request.headers.get('cookie') ?? undefined;
}

export function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}

export function writable(request: Request): boolean {
  const origin = request.headers.get('origin');
  const requestOrigin = new URL(request.url).origin;
  const configured = process.env.FRONTEND_ORIGIN
    ? new URL(process.env.FRONTEND_ORIGIN).origin
    : requestOrigin;
  const originOk = origin === requestOrigin || origin === configured;
  return originOk && request.headers.get('content-type')?.split(';')[0] === 'application/json';
}

async function backendRequest(
  path: '/auth/register' | '/auth/login' | '/auth/logout' | '/auth/me',
  body?: unknown,
  token?: string,
): Promise<Response> {
  const base = backendUrl();
  if (!base) throw new Error('Backend unavailable');
  return fetch(`${base}${path}`, {
    method: path === '/auth/me' ? 'GET' : 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    signal: AbortSignal.timeout(10000),
    redirect: 'manual',
  });
}

interface Identity {
  userId: string;
  displayName: string;
  email: string;
  fullName: string | null;
  role: string;
  expiresAt: string;
}

async function currentIdentity(request: Request): Promise<Identity | null> {
  if (!backendUrl()) return null;
  const token = readCookie(cookieHeader(request), SESSION_COOKIE);
  if (!token) return null;
  const response = await backendRequest('/auth/me', undefined, token);
  if (response.status === 401) return null;
  if (!response.ok) throw new Error('Backend identity unavailable');
  const data = (await response.json()) as {
    inquirer_id: string;
    login_name: string;
    role: string;
    expires_at: string;
  };
  return {
    userId: `backend:${data.inquirer_id}`,
    displayName: data.login_name,
    email: '',
    fullName: null,
    role: data.role,
    expiresAt: data.expires_at,
  };
}

const businessMessages: Record<number, string> = {
  401: '로그인이 만료되었습니다. 다시 로그인해 주세요.',
  403: '이 상담에 접근할 수 없습니다.',
  404: '학원 또는 상담을 찾을 수 없습니다.',
  409: '같은 요청 번호로 다른 내용을 제출할 수 없습니다. 내용을 확인해 주세요.',
  422: '입력한 학원, 학생 정보와 질문을 확인해 주세요.',
  429: '요청이 많습니다. 잠시 후 다시 시도해 주세요.',
};

async function businessRequest(
  request: Request,
  path: string,
  body?: unknown,
  key?: string,
): Promise<Response> {
  try {
    const base = backendUrl();
    if (!base) return json({ message: '상담 서비스 연결을 준비하고 있습니다.' }, 503);
    const isPublic = path.startsWith('/api/options') || path.startsWith('/api/academies');
    const token = isPublic ? undefined : readCookie(cookieHeader(request), SESSION_COOKIE) ?? undefined;
    if (!isPublic && !token) return json({ message: businessMessages[401] }, 401);
    const upstream = await fetch(base + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(key ? { 'Idempotency-Key': key } : {}),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: AbortSignal.timeout(10000),
      redirect: 'manual',
    });
    if (!upstream.ok) {
      const status = businessMessages[upstream.status] ? upstream.status : 502;
      const response = json({ message: businessMessages[status] || '상담 서비스에 연결할 수 없습니다. 다시 시도해 주세요.' }, status);
      if (status === 401) {
        response.headers.set('Set-Cookie', sessionCookie(request.url));
      }
      return response;
    }
    return json(await upstream.json(), upstream.status);
  } catch {
    return json({ message: '상담 서비스에 연결할 수 없습니다. 다시 시도해 주세요.' }, 502);
  }
}

const authMessages: Record<number, string> = {
  401: '아이디 또는 비밀번호를 확인해 주세요.',
  409: '이미 사용 중인 아이디입니다.',
  422: '아이디는 영문 소문자로 시작하는 3~32자, 비밀번호는 12~128자로 입력해 주세요.',
  429: '로그인이 일시적으로 잠겼어요. 5분 후 다시 시도해 주세요.',
};

export async function handleApi(request: Request): Promise<Response | null> {
  const url = new URL(request.url);
  const path = url.pathname;

  if (!path.startsWith('/api/')) return null;

  // /api/auth/:action
  const authMatch = path.match(/^\/api\/auth\/(register|login|logout)$/);
  if (authMatch) {
    if (request.method !== 'POST') return json({ message: '잘못된 요청입니다.' }, 404);
    if (!writable(request)) return json({ message: '요청을 확인해 주세요.' }, 403);
    const action = authMatch[1] as 'register' | 'login' | 'logout';
    try {
      if (!backendUrl()) return json({ message: '계정 서비스를 사용할 수 없습니다.' }, 503);
      let body: { login_name: string; password: string; terms_agreed?: boolean } | undefined;
      if (action !== 'logout') {
        const input = (await request.json()) as Record<string, unknown>;
        if (
          !input ||
          typeof input.login_name !== 'string' ||
          typeof input.password !== 'string' ||
          !/^[a-z][a-z0-9_]{2,31}$/.test(input.login_name) ||
          [...input.password].length < 12 ||
          [...input.password].length > 128
        ) {
          return json({ message: authMessages[422] }, 422);
        }
        body = { login_name: input.login_name, password: input.password };
        if (action === 'register') {
          if (input.terms_agreed !== true) {
            return json({ message: '회원가입을 진행하려면 이용약관에 동의해 주세요.' }, 422);
          }
          body.terms_agreed = true;
        }
      }
      const token =
        action === 'logout' ? readCookie(cookieHeader(request), SESSION_COOKIE) ?? undefined : undefined;
      if (action === 'logout' && !token) {
        const response = json({ logged_out: true });
        response.headers.set('Set-Cookie', sessionCookie(request.url));
        return response;
      }
      const upstream = await backendRequest(`/auth/${action}`, body, token);
      if (action === 'logout' && (upstream.ok || upstream.status === 401)) {
        const response = json({ logged_out: true });
        response.headers.set('Set-Cookie', sessionCookie(request.url));
        return response;
      }
      if (!upstream.ok) {
        return json(
          { message: authMessages[upstream.status] || '계정 서비스에 연결할 수 없어요. 다시 시도해 주세요.' },
          [401, 409, 422, 429].includes(upstream.status) ? upstream.status : 502,
        );
      }
      if (action === 'register') return json({ registered: true, login_name: body!.login_name }, 201);
      const data = (await upstream.json()) as { access_token: string; expires_at: string };
      const duration = Math.floor((Date.parse(data.expires_at) - Date.now()) / 1000);
      if (!data.access_token || !Number.isFinite(duration) || duration <= 0) {
        throw new Error('Invalid session');
      }
      const response = json({ logged_in: true });
      response.headers.set(
        'Set-Cookie',
        sessionCookie(request.url, data.access_token, Math.min(duration, 86400)),
      );
      return response;
    } catch (error) {
      return json(
        {
          message:
            error instanceof SyntaxError
              ? '입력 내용을 확인해 주세요.'
              : '계정 서비스에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.',
        },
        error instanceof SyntaxError ? 400 : 502,
      );
    }
  }

  if (path === '/api/account') {
    if (request.method === 'GET') {
      if (!backendUrl()) return json({ message: '계정 서비스에 연결할 수 없어요.' }, 503);
      try {
        const user = await currentIdentity(request);
        const response = json(
          {
            mode: 'backend',
            user: user ? { displayName: user.displayName, registered: true } : null,
          },
          user ? 200 : 401,
        );
        if (!user) response.headers.set('Set-Cookie', sessionCookie(request.url));
        return response;
      } catch {
        return json({ message: '계정 서비스에 연결할 수 없어요.' }, 502);
      }
    }
    return json({ message: '회원가입 화면을 이용해 주세요.' }, 400);
  }

  if (path === '/api/options' && request.method === 'GET') {
    return businessRequest(request, '/api/options');
  }

  if (path === '/api/academies' && request.method === 'GET') {
    return businessRequest(request, '/api/academies');
  }

  if (path === '/api/inquiries') {
    if (request.method === 'GET') {
      const params = url.searchParams;
      const limit = params.get('limit') ?? '10';
      const offset = params.get('offset') ?? '0';
      if (
        !/^\d+$/.test(limit) ||
        +limit < 1 ||
        +limit > 100 ||
        !/^\d+$/.test(offset) ||
        !Number.isSafeInteger(+offset)
      ) {
        return json({ message: '조회 범위를 확인해 주세요.' }, 422);
      }
      return businessRequest(request, `/api/inquiries?limit=${+limit}&offset=${+offset}`);
    }
    if (request.method === 'POST') {
      if (!writable(request)) return json({ message: '요청을 확인해 주세요.' }, 403);
      const key = request.headers.get('Idempotency-Key');
      if (!key || !/^[A-Za-z0-9_-]{1,80}$/.test(key)) {
        return json({ message: '요청 번호를 확인해 주세요.' }, 422);
      }
      try {
        if (!backendUrl()) return json({ message: '상담 서비스 연결을 준비하고 있습니다.' }, 503);
        const user = await currentIdentity(request);
        if (!user) return json({ message: '로그인이 필요합니다.' }, 401);
        const body = (await request.json()) as Record<string, unknown>;
        if (!body || typeof body !== 'object' || Array.isArray(body)) {
          return json({ message: '입력 내용을 확인해 주세요.' }, 400);
        }
        return businessRequest(
          request,
          '/api/inquiries',
          {
            inquirer_id: user.userId.slice('backend:'.length),
            academy_id: body.academy_id,
            student: body.student,
            question_codes: body.question_codes,
          },
          key,
        );
      } catch (error) {
        return json(
          {
            message:
              error instanceof SyntaxError
                ? '입력 내용을 확인해 주세요.'
                : '상담 서비스에 연결할 수 없습니다.',
          },
          error instanceof SyntaxError ? 400 : 502,
        );
      }
    }
  }

  const inquiryMatch = path.match(/^\/api\/inquiries\/([^/]+)$/);
  if (inquiryMatch && request.method === 'GET') {
    const id = decodeURIComponent(inquiryMatch[1]);
    if (!/^[A-Za-z0-9_-]{1,36}$/.test(id)) {
      return json({ message: '상담 번호를 확인해 주세요.' }, 404);
    }
    return businessRequest(request, `/api/inquiries/${encodeURIComponent(id)}`);
  }

  return json({ message: '잘못된 요청입니다.' }, 404);
}

/** Connect-style middleware for Vite. */
export function apiMiddleware() {
  return async (
    req: { url?: string; method?: string; headers: Record<string, string | string[] | undefined>; on: (ev: string, cb: (chunk?: Buffer) => void) => void; rawHeaders?: string[] },
    res: {
      statusCode: number;
      setHeader: (k: string, v: string) => void;
      end: (body?: string) => void;
    },
    next: () => void,
  ) => {
    const url = req.url || '/';
    if (!url.startsWith('/api/')) return next();

    const headers = new Headers();
    for (const [k, v] of Object.entries(req.headers)) {
      if (typeof v === 'string') headers.set(k, v);
      else if (Array.isArray(v)) headers.set(k, v.join(', '));
    }

    const method = req.method || 'GET';
    let body: Buffer | undefined;
    if (method !== 'GET' && method !== 'HEAD') {
      const chunks: Buffer[] = [];
      await new Promise<void>((resolve) => {
        req.on('data', (chunk?: Buffer) => {
          if (chunk) chunks.push(chunk);
        });
        req.on('end', () => resolve());
      });
      body = Buffer.concat(chunks);
    }

    const host = headers.get('host') || 'localhost';
    const request = new Request(`http://${host}${url}`, {
      method,
      headers,
      body: body && body.length ? new Uint8Array(body) : undefined,
    });

    const response = await handleApi(request);
    if (!response) return next();

    res.statusCode = response.status;
    response.headers.forEach((value, key) => {
      res.setHeader(key, value);
    });
    res.end(await response.text());
  };
}
