export type InquiryStatus = 'queued' | 'calling' | 'retry_wait' | 'completed' | 'failed';

export type AnswerViewKind = 'unknown' | 'time' | 'no' | 'yes';

export interface Student {
  grade: string;
  subject: string;
  level: string;
  region: string;
}

export interface Academy {
  academy_id: string;
  name: string;
  region: string;
  is_mock?: boolean;
  is_test?: boolean;
  can_submit?: boolean;
  notice?: string;
}

export interface InquiryQuestion {
  question_id: string;
  question_code: string;
}

export interface InquiryAnswer extends InquiryQuestion {
  asked?: boolean;
  answered?: boolean;
  yes_no?: boolean | null;
  reason?: string | null;
  detail?: string | null;
}

export interface InquiryAttempt {
  call_id: string;
  attempt_no: number;
  status: string;
  started_at: string;
  outcome?: string | null;
}

export interface InquiryResult {
  answers: InquiryAnswer[];
  summary_text?: string;
  notes?: string;
  consult_accepted?: boolean | null;
  available_times?: string[];
}

export interface InquiryDetail {
  inquiry_id: string;
  status: InquiryStatus;
  created_at: string;
  student: Student;
  academy: Academy;
  questions: InquiryQuestion[];
  attempts?: InquiryAttempt[];
  result?: InquiryResult | null;
  failure_reason?: string | null;
  review_required?: boolean;
  review_reason?: string | null;
}

export interface InquiryListItem {
  inquiry_id: string;
  status: InquiryStatus;
  created_at: string;
}

export interface CatalogOptions {
  question_codes: Record<string, string>;
  regions: string[];
  grade: string[];
  subject: string[];
  level: string[];
}

export interface SubmissionKey {
  fingerprint: string;
  key: string;
}

export interface FormValues {
  academy_id: string;
  grade: string;
  subject: string;
  level: string;
  region: string;
  question_codes: string[];
  real_test_confirm?: boolean;
}

export const states: Record<InquiryStatus, string> = {
  queued: '처리 대기',
  calling: '통화 중',
  retry_wait: '재시도 대기',
  completed: '상담 완료',
  failed: '처리 실패',
};

export const active = (status: string): boolean =>
  ['queued', 'calling', 'retry_wait'].includes(status);

export const reasons: Record<string, string> = {
  unknown: '학원에서 답변을 확인하지 못했습니다.',
  refused: '학원에서 답변을 거절했습니다.',
  not_asked: '이 질문을 아직 묻지 못했습니다.',
};

export const failureReasons: Record<string, string> = {
  real_test_disabled: '실통화 시험이 비활성화되어 발신하지 않았습니다.',
  retry_exhausted: '연락 시도 한도에 도달했습니다. 실통화 시험은 자동 재발신하지 않습니다.',
  no_answer: '학원에서 전화를 받지 않았습니다.',
  busy: '학원이 통화 중입니다.',
  rejected: '학원에서 통화를 거절했습니다.',
  machine: '자동 응답으로 연결되었습니다.',
  invalid_number: '학원 전화번호를 확인해야 합니다.',
  disclosure_missing: '상담 안내가 확인되지 않아 중단되었습니다.',
  delivery_or_result_timeout: '통화 연결 또는 결과 확인 시간이 초과되었습니다.',
};

export function fieldLabel(kind: string, code: string): string {
  if (kind === 'grade' && /^[EMH]\d$/.test(code)) {
    const school = ({ E: '초등학교', M: '중학교', H: '고등학교' } as Record<string, string>)[code[0]] ?? '';
    return `${school} ${code.slice(1)}학년`;
  }
  const maps: Record<string, Record<string, string>> = {
    subject: { KOR: '국어', ENG: '영어', MATH: '수학', SCI: '과학', SOC: '사회' },
    level: { HIGH: '상급', MID: '중급', LOW: '기초' },
  };
  return maps[kind]?.[code] || code;
}

export interface AnswerView {
  kind: AnswerViewKind;
  label: string;
  reason: string;
  detail: string;
}

export function answerView(answer?: InquiryAnswer | null): AnswerView {
  if (answer?.answered !== true) {
    return {
      kind: 'unknown',
      label: '미확인',
      reason: (answer?.reason && reasons[answer.reason]) || '확인된 답변이 없습니다.',
      detail: answer?.detail || '',
    };
  }
  if (answer.question_code === 'class_time') {
    return { kind: 'time', label: '시간 확인', reason: '', detail: answer.detail || '' };
  }
  if (answer.yes_no === false) {
    return { kind: 'no', label: '불가', reason: '', detail: answer.detail || '' };
  }
  if (answer.yes_no === true) {
    return { kind: 'yes', label: '가능', reason: '', detail: answer.detail || '' };
  }
  return { kind: 'unknown', label: '미확인', reason: '답변을 추가로 확인해야 합니다.', detail: answer.detail || '' };
}

export function inquiryPayload(form: FormValues) {
  return {
    academy_id: form.academy_id,
    student: {
      grade: form.grade,
      subject: form.subject,
      level: form.level,
      region: form.region,
    },
    question_codes: [...form.question_codes],
  };
}

export function submissionKey(
  previous: SubmissionKey | null | undefined,
  payload: unknown,
  random: () => string = () => crypto.randomUUID(),
): SubmissionKey {
  const fingerprint = JSON.stringify(payload);
  return previous?.fingerprint === fingerprint
    ? previous
    : { fingerprint, key: random() };
}
