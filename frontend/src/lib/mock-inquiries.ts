import type { Academy, CatalogOptions, InquiryDetail, InquiryListItem, InquiryStatus } from './inquiry-model';

const namespace = 'hakwon:isolated-mock:v1';

export const mockOptions: CatalogOptions = {
  question_codes: {
    shuttle: '셔틀 운행',
    pickup: '픽업 가능 여부',
    level_fit: '수준에 맞는 반',
    vacancy: '잔여 정원',
    level_test: '레벨 테스트',
    class_time: '수업 시간',
  },
  regions: ['대구 북구 침산동', '대구 북구 태전동', '대구 수성구 범어동'],
  grade: ['E1', 'E2', 'E3', 'E4', 'E5', 'E6', 'M1', 'M2', 'M3', 'H1', 'H2', 'H3'],
  subject: ['KOR', 'ENG', 'MATH', 'SCI', 'SOC'],
  level: ['HIGH', 'MID', 'LOW'],
};

const academy: Academy = {
  academy_id: 'mock-academy',
  name: '미리보기 학원',
  region: mockOptions.regions[0],
  is_mock: true,
};

export const mockAcademies: Academy[] = [academy];

interface MockRow extends InquiryDetail {
  // fixture rows already match InquiryDetail
}

interface MockStore {
  rows: MockRow[];
  keys: Record<string, string>;
}

function fixtures(): MockRow[] {
  const statuses: InquiryStatus[] = ['queued', 'calling', 'retry_wait', 'completed', 'failed'];
  return statuses.map((status, index) => {
    const id = `mock-${status}`;
    const questions = Object.keys(mockOptions.question_codes).map((code, i) => ({
      question_id: `${id}-q${i}`,
      question_code: code,
    }));
    const answers = questions.map((q, i) => ({
      ...q,
      asked: i !== 4,
      answered: [0, 1, 5].includes(i),
      yes_no: i === 0 ? true : i === 1 ? false : null,
      reason: i === 2 ? 'unknown' : i === 3 ? 'refused' : i === 4 ? 'not_asked' : null,
      detail: [
        '침산동 정류장에서 운행합니다.',
        '해당 지역 픽업은 운영하지 않습니다.',
        '담당 선생님 확인이 필요합니다.',
        '정원 정보는 전화로 안내하지 않습니다.',
        '통화 종료로 질문하지 못했습니다.',
        '화요일·목요일 19:00~20:30',
      ][i],
    }));
    return {
      inquiry_id: id,
      status,
      created_at: new Date(Date.now() - index * 600000).toISOString(),
      student: { grade: 'M2', subject: 'MATH', level: 'MID', region: academy.region },
      academy,
      questions,
      attempts:
        status === 'queued'
          ? []
          : [
              {
                call_id: `${id}-call`,
                attempt_no: 1,
                status: status === 'calling' ? 'answered' : 'finished',
                started_at: new Date().toISOString(),
                outcome: status === 'failed' ? 'no_answer' : null,
              },
            ],
      result:
        status === 'completed'
          ? {
              answers,
              summary_text: '질문별로 확인한 내용과 추가 확인이 필요한 내용을 정리했습니다.',
              notes: '상담 가능 시간은 예약 확정을 의미하지 않습니다.',
              consult_accepted: true,
              available_times: ['평일 14:00~16:00'],
            }
          : null,
      failure_reason: status === 'failed' ? 'retry_exhausted' : null,
      review_required: status === 'retry_wait',
      review_reason: status === 'retry_wait' ? 'callback_time_unknown' : null,
    };
  });
}

function load(): MockStore {
  try {
    const raw = sessionStorage.getItem(namespace);
    if (raw) {
      const data = JSON.parse(raw) as MockStore;
      if (data && Array.isArray(data.rows) && data.keys) return data;
    }
  } catch {
    /* ignore */
  }
  return { rows: fixtures(), keys: {} };
}

let data: MockStore = load();

function save() {
  try {
    sessionStorage.setItem(namespace, JSON.stringify(data));
  } catch {
    /* ignore */
  }
}

export function resetMock() {
  data = { rows: fixtures(), keys: {} };
  save();
}

export async function mockRequest(
  path: string,
  init: { method?: string; body?: string; headers?: Record<string, string> } = {},
  fault: 'normal' | 'loading' | 'error' = 'normal',
): Promise<unknown> {
  await new Promise((resolve) => setTimeout(resolve, fault === 'loading' ? 3000 : 180));
  if (fault === 'error') {
    throw Object.assign(
      new Error('미리보기 오류 상태입니다. 정상 응답으로 변경하고 다시 시도해 주세요.'),
      { status: 502 },
    );
  }
  if (path === '/api/options') return structuredClone(mockOptions);
  if (path === '/api/academies') return structuredClone(mockAcademies);
  if (path.startsWith('/api/inquiries?')) {
    const url = new URL(path, 'https://mock.invalid');
    const offset = Number(url.searchParams.get('offset') || 0);
    const limit = Number(url.searchParams.get('limit') || 10);
    return structuredClone(
      data.rows.slice(offset, offset + limit).map((r) => ({
        inquiry_id: r.inquiry_id,
        status: r.status,
        created_at: r.created_at,
      })),
    ) satisfies InquiryListItem[];
  }
  if (path === '/api/inquiries' && init.method === 'POST') {
    const payload = JSON.parse(init.body || '{}') as {
      academy_id: string;
      student: InquiryDetail['student'];
      question_codes: string[];
    };
    const key = init.headers?.['Idempotency-Key'] || '';
    if (data.keys[key]) {
      const row = data.rows.find((r) => r.inquiry_id === data.keys[key]);
      return { inquiry_id: data.keys[key], status: row?.status, duplicate: true };
    }
    const id = `mock-${crypto.randomUUID().slice(0, 25)}`;
    const row: MockRow = {
      inquiry_id: id,
      status: 'queued',
      created_at: new Date().toISOString(),
      student: payload.student,
      academy,
      questions: payload.question_codes.map((code, i) => ({ question_id: `${id}-${i}`, question_code: code })),
      attempts: [],
      result: null,
    };
    data.rows.unshift(row);
    data.keys[key] = id;
    save();
    return { inquiry_id: id, status: 'queued', duplicate: false };
  }
  if (path.startsWith('/api/inquiries/')) {
    const row = data.rows.find((r) => r.inquiry_id === decodeURIComponent(path.split('/').pop() || ''));
    if (row) return structuredClone(row);
    throw Object.assign(new Error('상담을 찾을 수 없습니다.'), { status: 404 });
  }
  throw new Error('미리보기에서 지원하지 않는 요청입니다.');
}
