import { type ReactNode } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

const crumbs: Record<string, string> = {
  '': '상담 홈',
  overview: '상담 홈',
  tasks: '내 상담',
  new: '새 상담',
  detail: '상담 상세',
  login: '로그인',
  register: '회원가입',
};

function AccountNav() {
  const { ready, error, user, mockMode, logout } = useAuth();
  const location = useLocation();

  if (mockMode) {
    return <span className="member-name">미리보기 전용</span>;
  }
  if (!ready) return <span className="muted">계정 확인 중…</span>;
  if (error) return <Link to="/login">계정 다시 확인</Link>;
  if (user) {
    return (
      <>
        <span className="member-name">{user.displayName}님</span>
        {user.registered ? (
          <button className="account-link logout-button" type="button" onClick={() => void logout()}>
            로그아웃
          </button>
        ) : (
          <Link className="button primary compact" to="/register">
            가입 완료하기
          </Link>
        )}
      </>
    );
  }
  return (
    <>
      <Link className="account-link" to="/login" state={{ from: location.pathname }}>
        로그인
      </Link>
      <Link className="button primary compact" to="/register">
        회원가입
      </Link>
    </>
  );
}

export default function Shell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const segment = location.pathname.split('/').filter(Boolean)[0] || 'overview';
  const crumb = crumbs[segment] || '상담 홈';

  return (
    <>
      <aside className="sidebar">
        <Link className="brand" to="/" aria-label="학원의신 홈">
          <img className="logo" src="/brand-mark.svg" alt="" />
          <span>
            학원의신<small>AI CONSULTATION</small>
          </span>
        </Link>
        <div className="nav-label">AI 상담</div>
        <nav>
          <NavLink to="/" end>
            ◫ <span>상담 홈</span>
          </NavLink>
          <NavLink to="/tasks">
            ☷ <span>내 상담</span>
          </NavLink>
          <NavLink to="/new">
            ＋ <span>새 상담</span>
          </NavLink>
        </nav>
        <div className="side-note">
          <div className="signal" aria-hidden="true">
            ▂ ▅ ▃ ▇ ▄ ▆ ▂
          </div>
          <b>
            질문은 간편하게.
            <br />
            선택은 확신 있게.
          </b>
          <p>
            반복되는 학원 문의,
            <br />
            학원의신 AI와 함께 준비하세요.
          </p>
          <Link to="/new">상담 준비하기 ↗</Link>
        </div>
        <div className="side-signature">학원을 알아보는 더 나은 방법.</div>
      </aside>
      <div className="shell">
        <header>
          <span>
            학원의신 <i>/</i> <span id="crumb">{crumb}</span>
          </span>
          <div id="account-nav">
            <AccountNav />
          </div>
        </header>
        <main id="app">{children}</main>
        <footer>
          <b>학원의신</b>
          <span>우리 아이에게 맞는 선택, 더 명확하게.</span>
          <span>AI CONSULTATION</span>
        </footer>
      </div>
    </>
  );
}
