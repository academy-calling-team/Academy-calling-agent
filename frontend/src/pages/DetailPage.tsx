import { Link, useParams } from 'react-router-dom';
import { useInquiryDetail } from '../hooks/useInquiries';
import { usePolling, shouldPollDetail } from '../hooks/usePolling';
import { ErrorPanel, Loading, StatusBadge } from '../components/ui';
import {
  active,
  answerView,
  failureReasons,
  fieldLabel,
  states,
  type InquiryDetail,
} from '../lib/inquiry-model';

function formatKst(value?: string) {
  return value ? new Date(value).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) : '';
}

function Answers({ detail, questionLabels }: { detail: InquiryDetail; questionLabels: Record<string, string> }) {
  return (
    <>
      {(detail.questions || []).map((q) => {
        const answer = detail.result?.answers?.find(
          (a) => a.question_id === q.question_id || a.question_code === q.question_code,
        );
        const view = answerView(answer);
        return (
          <div className={`answer ${view.kind}`} data-answer-kind={view.kind} key={q.question_id}>
            <span className="answer-symbol">{view.kind === 'unknown' ? '?' : view.kind === 'no' ? '−' : '✓'}</span>
            <div>
              <h3>{questionLabels[q.question_code] || q.question_code}</h3>
              {view.detail ? <p>{view.detail}</p> : null}
              {view.reason ? <p className="answer-reason">미확인 사유: {view.reason}</p> : null}
            </div>
            <span className={`badge ${view.kind === 'unknown' ? 'review' : view.kind === 'no' ? 'failed' : ''}`}>
              {view.label}
            </span>
          </div>
        );
      })}
    </>
  );
}

export default function DetailPage() {
  const { id } = useParams();
  const inquiryId = id ? decodeURIComponent(id) : undefined;
  const { state, detail, error, updated, reload } = useInquiryDetail(inquiryId);

  usePolling({
    enabled: shouldPollDetail(detail?.status),
    onTick: () => reload(),
    hasError: Boolean(error),
  });

  if (!detail) {
    return state === 'error' ? (
      <ErrorPanel message={error} onAction={() => void reload()} />
    ) : (
      <Loading text="상담 내용을 불러오고 있어요." />
    );
  }

  const t = detail;
  const phase = t.status === 'queued' ? 0 : ['calling', 'retry_wait'].includes(t.status) ? 1 : 2;
  const descriptions: Record<string, string> = {
    queued: '상담이 접수되었습니다. 운영 시간과 처리 순서에 맞춰 연락을 준비합니다.',
    calling: '선택한 질문을 확인하고 있습니다. 통화가 끝나면 결과를 정리합니다.',
    retry_wait: t.review_required
      ? '재연락 시간을 확인하지 못해 검토를 기다리고 있습니다. 자동 재발신은 보류됩니다.'
      : '학원과 연결되지 않아 다시 연락할 순서를 기다리고 있습니다.',
    completed: '상담 처리가 완료되었습니다. 확인된 답변과 미확인 항목을 구분해 확인하세요.',
    failed:
      failureReasons[t.failure_reason || ''] ||
      '상담을 완료하지 못했습니다. 확인되지 않은 답변을 불가로 판단하지 않습니다.',
  };

  return (
    <>
      <Link className="back" to="/tasks">
        ← 내 상담으로
      </Link>
      <div className="refresh-row">
        <span>
          {active(t.status) ? '5초마다 상태를 확인합니다.' : '최종 처리 상태'}
          {updated ? ` · ${formatKst(updated)}` : ''}
        </span>
        <button className="button" type="button" onClick={() => void reload()} disabled={state === 'loading'}>
          {state === 'loading' ? '확인 중…' : '새로고침'}
        </button>
      </div>
      {error ? <ErrorPanel message={error} onAction={() => void reload()} /> : null}
      <div className="content-grid">
        <section className="panel">
          <div className="detail-head">
            <div className="eyebrow">INQUIRY {t.inquiry_id}</div>
            <div className="detail-title">
              <div className="academy-icon">⌂</div>
              <h1>{t.academy?.name}</h1>
              <div className="status-badges">
                <StatusBadge status={t.status} reviewRequired={t.review_required} states={states} />
              </div>
            </div>
            <div className="meta">
              {fieldLabel('grade', t.student.grade)} · {fieldLabel('subject', t.student.subject)} ·{' '}
              {fieldLabel('level', t.student.level)} · {t.student.region}
            </div>
          </div>
          <div className="timeline">
            {['상담 접수', '전화 상담', '처리 결과'].map((label, i) => (
              <span key={label} className={i <= phase ? 'done' : ''}>
                {i < phase ? '✓' : i === phase ? '●' : '○'} {label}
              </span>
            ))}
          </div>
          <div className="result-body">
            <div className={`notice ${t.status === 'failed' ? 'failure-notice' : ''}`}>
              {descriptions[t.status] || '상담 상태를 확인하고 있습니다.'}
            </div>
            {t.academy?.is_mock === false ? (
              <p className="notice">실통화 시험 · 최대 1회 · 미응답 시 자동 재발신 없음</p>
            ) : null}
            {t.review_required ? (
              <p className="review-notice">
                확인 필요:{' '}
                {t.review_reason === 'callback_time_unknown'
                  ? '학원에서 재연락을 요청했으나 시간을 정하지 않았습니다.'
                  : t.review_reason || '추가 검토가 필요합니다.'}
              </p>
            ) : null}
            {t.result?.summary_text ? (
              <>
                <h2>상담 요약</h2>
                <p>{t.result.summary_text}</p>
              </>
            ) : null}
            <h2>항목별 상담 결과</h2>
            <Answers detail={t} questionLabels={{}} />
            {t.result?.notes ? (
              <div className="notice">
                <b>추가 안내</b>
                <br />
                {t.result.notes}
              </div>
            ) : null}
          </div>
        </section>
        <aside>
          <div className="tip-card">
            <div className="eyebrow">CONSULTATION</div>
            <h3>추가 상담 안내</h3>
            <p>
              {t.result?.consult_accepted === true
                ? '학원에서 추가 상담이 가능하다고 답변했습니다.'
                : t.result?.consult_accepted === false
                  ? '학원에서 추가 상담이 어렵다고 답변했습니다.'
                  : '추가 상담 가능 여부는 아직 확인되지 않았습니다.'}
            </p>
            {t.result?.available_times?.length ? (
              <>
                <ul>
                  {t.result.available_times.map((time) => (
                    <li key={time}>{time}</li>
                  ))}
                </ul>
                <p>가능한 시간이며 예약 확정이 아닙니다.</p>
              </>
            ) : null}
          </div>
          {t.attempts?.length ? (
            <div className="tip-card">
              <div className="eyebrow">CALL LOG</div>
              <h3>통화 시도</h3>
              <ul className="attempts">
                {t.attempts.map((a) => (
                  <li key={a.call_id}>
                    <p>
                      #{a.attempt_no} · {a.status}
                    </p>
                    <small>
                      {formatKst(a.started_at)}
                      {a.outcome ? ` · ${a.outcome}` : ''}
                    </small>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </aside>
      </div>
    </>
  );
}
