import type { InquiryDetail } from './inquiry-model';

export interface RetryView {
  kind: 'callback' | 'not_connected' | 'review' | 'unknown';
  label: string;
  description: string;
  requestedAt: string | null;
}

function requestedTime(value?: string | null): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value))) return null;
  return value;
}

export function retryView(detail?: InquiryDetail): RetryView | null {
  if (detail?.status !== 'retry_wait') return null;
  if (detail.review_required) {
    const callback = detail.review_reason === 'callback_time_unknown';
    return {
      kind: 'review',
      label: callback ? '재통화 시간 확인 중' : '재연락 검토 중',
      description: callback
        ? '학원과 통화했으며 재연락 요청을 받았습니다. 시간을 확인하는 동안 자동 재발신은 보류됩니다.'
        : '재연락 진행 여부를 검토하고 있습니다. 확인이 끝날 때까지 자동 재발신은 보류됩니다.',
      requestedAt: null,
    };
  }
  const latest = detail.attempts?.length ? detail.attempts.reduce((current, attempt) =>
    attempt.attempt_no > current.attempt_no ? attempt : current) : undefined;
  const outcome = latest ? latest.outcome : detail.result?.outcome;
  const nonConnected: Record<string, string> = {
    no_answer: '학원에서 전화를 받지 않아 다시 연락할 순서를 기다리고 있습니다.',
    busy: '학원 전화가 통화 중이어서 다시 연락할 순서를 기다리고 있습니다.',
    machine: '자동 응답으로 연결되어 학원 담당자와 다시 통화할 순서를 기다리고 있습니다.',
    rejected: '학원에서 전화를 거절하여 다시 연락할 순서를 기다리고 있습니다.',
  };
  if (outcome && Object.hasOwn(nonConnected, outcome)) {
    return { kind: 'not_connected', label: '연결 재시도 대기', description: nonConnected[outcome], requestedAt: null };
  }
  // A previous call's result can remain while a newer attempt is in progress.
  // Prefer the latest attempt's outcome; do not apply an old callback to a failed/new attempt.
  const callback = detail.result?.callback_requested === true && (!latest || outcome === 'answered');
  if (outcome === 'answered' || callback) {
    return {
      kind: 'callback',
      label: '통화 후 재연락 대기',
      description: callback
        ? '학원과 통화했으며 재연락 요청에 따라 다시 통화할 순서를 기다리고 있습니다.'
        : '학원과 통화한 뒤 다시 연락할 순서를 기다리고 있습니다.',
      requestedAt: callback ? requestedTime(detail.result?.callback_at) : null,
    };
  }
  return {
    kind: 'unknown', label: '재연락 대기',
    description: '다시 연락할 순서를 기다리고 있습니다. 이전 통화의 연결 여부와 재연락 사유는 아직 확인되지 않았습니다.',
    requestedAt: null,
  };
}
