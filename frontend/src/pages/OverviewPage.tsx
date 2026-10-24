import { Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useInquiryList } from '../hooks/useInquiries';
import { usePolling, shouldPollList } from '../hooks/usePolling';
import { ErrorPanel, Head, Loading } from '../components/ui';
import { states, type InquiryListItem } from '../lib/inquiry-model';

function formatKst(value?: string) {
  return value ? new Date(value).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) : '';
}

function Card({ item }: { item: InquiryListItem }) {
  return (
    <Link className="task" to={`/detail/${encodeURIComponent(item.inquiry_id)}`}>
      <div className="task-top">
        <div className="academy-icon">⌂</div>
        <div className="task-name">
          <h3>{item.inquiry_id}</h3>
          <small>상세 페이지에서 내용을 확인하세요.</small>
        </div>
        <div className="status-badges">
          <span className={`badge ${item.status}`}>{states[item.status] || '상태 확인 필요'}</span>
        </div>
      </div>
      <div className="task-bottom">
        <div className="tags" />
        <span>{formatKst(item.created_at)} ↗</span>
      </div>
    </Link>
  );
}

export default function OverviewPage() {
  const { user, ready, mockMode } = useAuth();
  const list = useInquiryList();
  const canSee = Boolean(user) || mockMode;

  usePolling({
    enabled: canSee && ready && shouldPollList(list.rows.map((r) => r.status)),
    onTick: () => list.reload(),
    hasError: Boolean(list.error),
  });

  return (
    <>
      <Head
        title={
          <>
            우리 아이의 다음 배움,
            <br />
            확신을 갖고 선택하세요.
          </>
        }
        desc="학원 문의부터 확인된 답변까지 한곳에서 살펴보세요."
        action={
          <Link className="button primary" to="/new">
            새 상담 시작하기
          </Link>
        }
      />
      <section className="hero">
        <div>
          <div className="eyebrow">LESS CALLING. MORE CLARITY.</div>
          <h2>
            궁금한 건 AI에게.
            <br />
            중요한 선택은 부모님께.
          </h2>
          <p>
            학원과 질문을 선택하고 상담 진행 상황을 확인하세요.
            <br />
            답변이 확인된 항목과 추가 확인이 필요한 항목을 구분합니다.
          </p>
          <Link className="button primary" to="/new">
            새 상담 시작하기
          </Link>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orbit">
            <div className="voice-icon">
              <i />
              <i />
              <i />
              <i />
              <i />
            </div>
          </div>
        </div>
      </section>
      <div className="section-head recent-head">
        <h2>최근 상담</h2>
        <Link to="/tasks">전체 보기 ↗</Link>
      </div>
      <div className="panel">
        {!canSee ? (
          <div className="empty">
            <h3>나의 상담을 확인하세요</h3>
            <p>로그인하면 상담 내역과 결과를 확인할 수 있습니다.</p>
            <Link className="button primary" to="/login">
              로그인
            </Link>
          </div>
        ) : list.state === 'loading' && !list.rows.length ? (
          <Loading text="상담 내역을 불러오고 있어요." />
        ) : list.state === 'error' && !list.rows.length ? (
          <ErrorPanel message={list.error} onAction={() => void list.reload()} />
        ) : list.rows.length ? (
          list.rows.slice(0, 5).map((item) => <Card key={item.inquiry_id} item={item} />)
        ) : (
          <div className="empty">
            <h3>표시할 상담이 없어요</h3>
            <p>선택한 조건을 바꾸거나 새 상담을 시작해 보세요.</p>
          </div>
        )}
      </div>
    </>
  );
}
