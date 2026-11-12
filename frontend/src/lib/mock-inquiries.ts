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
  const rows: MockRow[] = statuses.map((status, index) => {
    const id = `mock-${status}`;
    const questions = Object.keys(mockOptions.question_codes).map((code, i) => ({
      question_id: `${id}-q${i}`,
      question_code: code,
      question_label_kr: mockOptions.question_codes[code] || code,
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
      source_text: [
        '네, 침산동 정류장에서는 차량 운행하고 있어요.',
        '말씀하신 지역은 픽업을 하지 않아요.',
        '그건 담당 선생님께 한번 여쭤봐야 할 것 같아요.',
        '정원은 전화로 안내해 드리기 어려워요.',
        null,
        '화요일하고 목요일, 저녁 일곱 시부터 여덟 시 반까지예요.',
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
                status_label_kr: status === 'calling' ? '통화 중' : '통화 종료',
                started_at: new Date().toISOString(),
                outcome: status === 'failed' ? 'no_answer' : null,
                outcome_label_kr: status === 'failed' ? '부재중' : null,
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
  const base = rows.find((row) => row.status === 'retry_wait')!;
  const requested = new Date(Date.now() + 86400000);
  requested.setUTCHours(6, 0, 0, 0);
  const callback: MockRow = {
    ...base, inquiry_id: 'mock-callback-scheduled', review_required: false, review_reason: null,
    attempts: [{ call_id: 'mock-callback-call', attempt_no: 1, status: 'finished', status_label_kr: '통화 종료', outcome: 'answered', outcome_label_kr: '연결됨', started_at: base.created_at }],
    result: { answers: [], outcome: 'answered', callback_requested: true, callback_at: requested.toISOString(), summary_text: '학원에서 다음 날 오후 3시에 다시 연락해 달라고 요청했습니다.' },
  };
  const noAnswer: MockRow = {
    ...base, inquiry_id: 'mock-retry-no-answer', review_required: false, review_reason: null,
    attempts: [{ call_id: 'mock-no-answer-call', attempt_no: 1, status: 'finished', status_label_kr: '통화 종료', outcome: 'no_answer', outcome_label_kr: '부재중', started_at: base.created_at }],
  };
  const unknown: MockRow = { ...callback, inquiry_id: 'mock-callback-unknown', review_required: true, review_reason: 'callback_time_unknown', result: { ...callback.result!, callback_at: null, summary_text: '학원에서 재연락을 요청했지만 시간을 정하지 않았습니다.' } };
  return [...rows, callback, noAnswer, unknown];
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
      questions: payload.question_codes.map((code, i) => ({ question_id: `${id}-${i}`, question_code: code, question_label_kr: mockOptions.question_codes[code] || code })),
      attempts: [],
      result: null,
    };
    data.rows.unshift(row);
    data.keys[key] = id;
    save();
    return { inquiry_id: id, status: 'queued', duplicate: false };
  }
  if (path.startsWith('/api/inquiries/')) {
    const id = decodeURIComponent(path.split('/').pop() || '');
    const row = data.rows.find((r) => r.inquiry_id === id)
      || fixtures().find((r) => r.inquiry_id === id && ['mock-callback-scheduled', 'mock-retry-no-answer', 'mock-callback-unknown'].includes(id));
    if (row) return structuredClone(row);
    throw Object.assign(new Error('상담을 찾을 수 없습니다.'), { status: 404 });
  }
  throw new Error('미리보기에서 지원하지 않는 요청입니다.');
}
