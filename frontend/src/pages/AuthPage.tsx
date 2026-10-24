import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { submitBackendAuth, useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';

export default function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const register = mode === 'register';
  const { user, ready, error: authError, reload, logout, mockMode, pendingLogin, setPendingLogin } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [loginName, setLoginName] = useState(pendingLogin);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [terms, setTerms] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (mockMode) {
    return (
      <section className="auth-panel">
        <div className="eyebrow">ISOLATED PREVIEW</div>
        <h1>미리보기 전용 모드</h1>
        <p>격리된 미리보기에서는 실제 계정 기능을 사용하지 않습니다.</p>
        <Link className="button primary" to="/tasks">
          미리보기로 돌아가기 ↗
        </Link>
      </section>
    );
  }

  if (!ready) {
    return <div className="empty">계정 정보를 확인하고 있어요.</div>;
  }

  if (authError) {
    return (
      <section className="auth-panel">
        <h1>계정 정보를 확인할 수 없어요</h1>
        <p>잠시 후 다시 시도해 주세요.</p>
        <button className="button primary" type="button" onClick={() => void reload()}>
          다시 시도
        </button>
      </section>
    );
  }

  if (user?.registered) {
    return (
      <section className="auth-panel">
        <div className="eyebrow">MY ACCOUNT</div>
        <h1>{user.displayName}님</h1>
        <p>학원의신에 로그인되어 있어요.</p>
        <Link className="button primary" to="/tasks">
          내 상담 보기 ↗
        </Link>
        <button className="logout-button" type="button" onClick={() => void logout()}>
          로그아웃
        </button>
      </section>
    );
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError('');
    if (register && password !== confirm) {
      setFormError('비밀번호가 일치하지 않습니다.');
      return;
    }
    if (register && !terms) {
      setFormError('이용약관에 동의해 주세요.');
      return;
    }
    setSubmitting(true);
    try {
      await submitBackendAuth(register ? 'register' : 'login', {
        login_name: loginName,
        password,
        ...(register ? { terms_agreed: terms } : {}),
      });
      setPendingLogin(loginName);
      setPassword('');
      setConfirm('');
      if (register) {
        setPendingLogin(loginName);
        navigate('/login');
        toast.show('가입이 완료되었습니다. 로그인해 주세요.');
      } else {
        setPendingLogin('');
        await reload();
        navigate('/');
        toast.show('로그인되었습니다.');
      }
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-layout">
      <section className="auth-brand">
        <div className="eyebrow">HAKWON AI · YOUR NEXT STEP</div>
        <h2>
          우리 아이의 배움,
          <br />
          더 명확한 답변으로.
        </h2>
        <p>
          학원에 궁금한 내용을 정리하고
          <br />
          나만의 상담 내역을 관리하세요.
        </p>
        <div className="auth-points">
          <span>✓ 계정별 상담 관리</span>
          <span>✓ 필요한 학습 정보만 전달</span>
          <span>✓ 안전한 계정 연결</span>
        </div>
      </section>
      <section className="auth-panel">
        <div className="eyebrow">{register ? 'CREATE ACCOUNT' : 'WELCOME BACK'}</div>
        <h1>{register ? '학원의신과 함께 시작하세요' : '다시 만나 반가워요'}</h1>
        <p>{register ? '아이디와 비밀번호로 회원가입하세요.' : '아이디와 비밀번호를 입력해 주세요.'}</p>
        <form onSubmit={onSubmit}>
          <label className="field">
            아이디
            <input
              name="login_name"
              required
              minLength={3}
              maxLength={32}
              pattern="[a-z][a-z0-9_]{2,31}"
              autoCapitalize="none"
              spellCheck={false}
              autoComplete="username"
              value={loginName}
              onChange={(e) => setLoginName(e.target.value)}
              placeholder="영문 소문자로 시작하는 아이디"
            />
          </label>
          <p className="summary-note">3~32자 · 영문 소문자, 숫자, 밑줄(_) 사용</p>
          <label className="field">
            비밀번호
            <div className="password-input">
              <input
                name="password"
                type={showPassword ? 'text' : 'password'}
                required
                minLength={12}
                maxLength={128}
                autoComplete={register ? 'new-password' : 'current-password'}
                placeholder="12~128자 비밀번호"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                aria-label="비밀번호 표시"
                aria-pressed={showPassword}
                onClick={() => setShowPassword((v) => !v)}
              >
                표시
              </button>
            </div>
          </label>
          {register ? (
            <>
              <label className="field">
                비밀번호 확인
                <input
                  name="confirm_password"
                  type={showPassword ? 'text' : 'password'}
                  required
                  minLength={12}
                  maxLength={128}
                  autoComplete="new-password"
                  placeholder="비밀번호를 다시 입력하세요"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                />
              </label>
              <label className="auth-terms">
                <input type="checkbox" name="terms_agreed" required checked={terms} onChange={(e) => setTerms(e.target.checked)} />
                이용약관에 동의합니다. (필수)
              </label>
            </>
          ) : null}
          <p id="auth-form-error" className="auth-error" role="alert" aria-live="polite">
            {formError}
          </p>
          <button className="button primary auth-continue" type="submit" disabled={submitting}>
            {submitting ? (register ? '가입 중…' : '로그인 중…') : register ? '회원가입 ↗' : '로그인 ↗'}
          </button>
        </form>
        <div className="auth-switch">
          {register ? (
            <>
              이미 계정이 있으신가요? <Link to="/login">로그인</Link>
            </>
          ) : (
            <>
              처음 이용하시나요? <Link to="/register">회원가입</Link>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
