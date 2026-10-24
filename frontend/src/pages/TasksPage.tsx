import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useInquiryList } from '../hooks/useInquiries';
import { usePolling, shouldPollList } from '../hooks/usePolling';
import { ErrorPanel, Head, Loading } from '../components/ui';
import { active, states, type InquiryListItem } from '../lib/inquiry-model';

function formatKst(value?: string) {
  return value ? new Date(value).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) : '';
}

const filters: Array<{ key: string; label: string }> = [
  { key: 'all', label: '전체' },
  { key: 'active', label: '진행 중' },
  { key: 'queued', label: '처리 대기' },
  { key: 'calling', label: '통화 중' },
  { key: 'retry_wait', label: '재시도 대기' },
  { key: 'completed', label: '완료' },
  { key: 'failed', label: '실패' },
  { key: 'review', label: '확인 필요' },
];

export default function TasksPage() {
  const { user, ready, mockMode } = useAuth();
  const list = useInquiryList();
  const canSee = Boolean(user) || mockMode;
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');

  usePolling({
    enabled: canSee && ready && shouldPollList(list.rows.map((r) => r.status)),
    onTick: () => list.reload(),
    hasError: Boolean(list.error),
  });

  const selected = useMemo(() => {
    return list.rows.filter((item) => {
      const t = list.details[item.inquiry_id] || item;
      const name = (t as { academy?: { name?: string } }).academy?.name || item.inquiry_id;
      if (query && !name.includes(query) && !item.inquiry_id.includes(query)) return false;
      if (filter === 'all') return true;
      if (filter === 'active') return active(item.status);
      if (filter === 'review') {
        const detail = list.details[item.inquiry_id];
        return Boolean(detail?.review_required) || Boolean(detail?.result?.answers?.some((a) => !a.answered));
      }
      return item.status === filter;
    });
  }, [list.rows, list.details, filter, query]);

  return (
    <>
      <Head
        title="내 상담"
        desc="진행 상태를 확인하고 상담 결과를 살펴보세요."
        action={
          <Link className="button primary" to="/new">
            새 상담 시작하기
          </Link>
        }
      />
      <div className="toolbar">
        <input
          className="search"
          id="search"
          aria-label="학원 검색"
          placeholder="학원 이름 검색"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="filters">
          {filters.map((f) => (
            <button
              key={f.key}
              type="button"
              className={`filter ${filter === f.key ? 'active' : ''}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      <div className="refresh-row">
        <span>
          {list.updated ? `마지막 확인 ${formatKst(list.updated)}` : '상담 내역 확인'} · 현재 페이지 검색
          {list.rows.some((t) => active(t.status)) ? ' · 5초마다 상태 확인' : ''}
        </span>
        <button
          className="button"
          type="button"
          onClick={() => void list.reload()}
          disabled={list.state === 'loading'}
        >
          {list.state === 'loading' ? '확인 중…' : '새로고침'}
        </button>
      </div>
      {list.error ? <ErrorPanel message={list.error} onAction={() => void list.reload()} /> : null}
      <div className="panel" id="rows">
        {!canSee ? (
          <div className="empty">
            <h3>로그인이 필요합니다</h3>
            <p>로그인하면 상담 내역과 결과를 확인할 수 있습니다.</p>
            <Link className="button primary" to="/login">
              로그인
            </Link>
          </div>
        ) : list.state === 'loading' && !list.rows.length ? (
          <Loading text="상담 내역을 불러오고 있어요." />
        ) : selected.length ? (
          selected.map((item: InquiryListItem) => {
            const t = list.details[item.inquiry_id] || item;
            const academy = (t as { academy?: { name?: string; region?: string } }).academy;
            const student = (t as { student?: { region?: string; grade?: string; subject?: string } }).student;
            return (
              <Link className="task" key={item.inquiry_id} to={`/detail/${encodeURIComponent(item.inquiry_id)}`}>
                <div className="task-top">
                  <div className="academy-icon">⌂</div>
                  <div className="task-name">
                    <h3>{academy?.name || item.inquiry_id}</h3>
                    <small>
                      {student
                        ? `${student.region} · ${student.grade} · ${student.subject}`
                        : '상세 페이지에서 내용을 확인하세요.'}
                    </small>
                  </div>
                  <div className="status-badges">
                    <span className={`badge ${item.status}`}>{states[item.status] || '상태 확인 필요'}</span>
                    {(t as { review_required?: boolean }).review_required ? (
                      <span className="badge review">확인 필요</span>
                    ) : null}
                  </div>
                </div>
                <div className="task-bottom">
                  <div className="tags">
                    {((t as { questions?: Array<{ question_code: string }> }).questions || []).map((q) => (
                      <span key={q.question_code}>{q.question_code}</span>
                    ))}
                  </div>
                  <span>{formatKst(item.created_at)} ↗</span>
                </div>
              </Link>
            );
          })
        ) : (
          <div className="empty">
            <h3>표시할 상담이 없어요</h3>
            <p>선택한 조건을 바꾸거나 새 상담을 시작해 보세요.</p>
          </div>
        )}
      </div>
      <div className="pagination">
        <button
          className="button"
          type="button"
          disabled={list.offset === 0 || list.state === 'loading'}
          onClick={() => list.setOffset(Math.max(0, list.offset - 10))}
        >
          이전
        </button>
        <span>{Math.floor(list.offset / 10) + 1} 페이지</span>
        <button
          className="button"
          type="button"
          disabled={!list.hasNext || list.state === 'loading'}
          onClick={() => list.setOffset(list.offset + 10)}
        >
          다음
        </button>
      </div>
    </>
  );
}
