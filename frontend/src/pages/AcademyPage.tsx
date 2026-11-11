import { useEffect, useRef, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useToast } from '../hooks/useToast';
import { days, emptyProfile, validateProfile, type AcademyProfile, type Preference } from '../lib/academy-model';
import { readAcademy, saveAcademy } from '../lib/mock-academy';
import { mockOptions } from '../lib/mock-inquiries';
import { fieldLabel } from '../lib/inquiry-model';
import { ApiError, api } from '../lib/api';
import { getAcademy, putAcademy } from '../lib/academy-api';

function levelLabel(code: string) {
  return code === 'HIGH' ? '심화' : fieldLabel('level', code);
}

function preferenceLabel(p: Preference) {
  return `${fieldLabel('subject', p.subject_code)} · ${fieldLabel('grade', p.grade_code)} · ${p.level_code ? levelLabel(p.level_code) : '수준 무관'}`;
}

export default function AcademyPage() {
  const { ready, error, user, mockMode, reload } = useAuth();
  if (!ready) return <div className="empty">계정 정보를 확인하고 있어요.</div>;
  if (error) return <div className="empty"><p>계정 정보를 확인할 수 없어요.</p><button className="button" onClick={() => void reload()}>다시 시도</button></div>;
  if (!user) return <Navigate to={'/login' + (mockMode ? '?preview=mock' : '')} replace />;
  if (user.accountType !== 'academy') return <Navigate to={'/' + (mockMode ? '?preview=mock' : '')} replace />;
  return <AcademyEditor key={user.userId} userId={user.userId!} />;
}

function AcademyEditor({ userId }: { userId: string }) {
  const { mockMode } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const [saved, setSaved] = useState<AcademyProfile | null>(() => mockMode ? readAcademy(userId) : null);
  const [profile, setProfile] = useState<AcademyProfile>(() => saved || emptyProfile());
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(!mockMode);
  const [loadFailed, setLoadFailed] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [options, setOptions] = useState(mockOptions);
  const [weights, setWeights] = useState([1, 1, 1]);
  const [bonuses, setBonuses] = useState([0, 0, 0, 0]);
  const dialog = useRef<HTMLDialogElement>(null);
  const dirty = JSON.stringify(profile) !== JSON.stringify(saved || emptyProfile());
  useEffect(() => {
    if (mockMode) return;
    let cancelled = false;
    setLoading(true);
    setLoadFailed(false);
    async function load() {
      try {
        const nextOptions = await api<typeof mockOptions>('/api/options');
        let next = null;
        try {
          next = await getAcademy();
        } catch (err) {
          if (!(err instanceof ApiError) || err.status !== 404) throw err;
        }
        if (cancelled) return;
        setOptions(nextOptions);
        setSaved(next);
        setProfile(next || emptyProfile());
      } catch {
        if (!cancelled) setLoadFailed(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [mockMode, userId, loadAttempt]);
  useEffect(() => {
    if (loading || loadFailed) return;
    const expected = saved ? '/academy/manage' : '/academy/register';
    if (location.pathname !== expected) navigate(expected + (mockMode ? '?preview=mock' : ''), { replace: true });
  }, [saved, location.pathname, navigate, mockMode, loading, loadFailed]);
  useEffect(() => {
    if (!dirty) return;
    function beforeUnload(event: BeforeUnloadEvent) { event.preventDefault(); }
    function intercept(event: MouseEvent) {
      const link = (event.target as Element).closest('a');
      if (link && link.href !== window.location.href && !window.confirm('저장하지 않은 변경 사항이 있습니다. 이동하시겠어요?')) { event.preventDefault(); event.stopPropagation(); }
    }
    window.addEventListener('beforeunload', beforeUnload);
    document.addEventListener('click', intercept, true);
    return () => { window.removeEventListener('beforeunload', beforeUnload); document.removeEventListener('click', intercept, true); };
  }, [dirty]);
  function update(patch: Partial<AcademyProfile>) { setProfile((p) => ({ ...p, ...patch })); setError(''); }
  function patchPreference(index: number, patch: Partial<Preference>) { update({ classes: profile.classes.map((p, i) => i === index ? { ...p, ...patch } : p) }); }
  async function save() {
    const message = validateProfile(profile);
    if (message) { setError(message); return; }
    setSaving(true);
    try {
      const next = mockMode ? saveAcademy(userId, profile) : await putAcademy(profile, saved === null);
      setSaved(next); setProfile(next); dialog.current?.close();
      toast.show(mockMode ? '미리보기 학원 정보가 저장되었습니다.' : '학원 정보가 저장되었습니다.');
    } catch (err) {
      dialog.current?.close();
      setError(err instanceof ApiError && err.status === 409
        ? '이미 등록되었거나 다른 화면에서 수정되었습니다. 페이지를 새로고침해 최신 정보를 확인해 주세요.'
        : '저장하지 못했습니다. 입력 내용과 연결 상태를 확인해 주세요.');
    }
    finally { setSaving(false); }
  }
  const inquiries = [
    { subject_code: 'SOC', grade_code: 'E6', level_code: 'LOW' },
    { subject_code: 'MATH', grade_code: 'M1', level_code: 'LOW' },
    { subject_code: 'MATH', grade_code: 'M1', level_code: 'MID' },
    { subject_code: 'ENG', grade_code: 'H1', level_code: 'HIGH' },
  ].map((q, id) => {
    const match = Math.max(0, ...profile.classes.map((p) => (p.subject_code === q.subject_code ? weights[0] : 0) + (p.grade_code === q.grade_code ? weights[1] : 0) + (p.level_code !== null && p.level_code === q.level_code ? weights[2] : 0)));
    return { ...q, id, match, score: match + bonuses[id] };
  }).sort((a, b) => b.score - a.score || a.id - b.id);
  if (loading) return <div className="empty">학원 정보를 불러오고 있어요.</div>;
  if (loadFailed) return <div className="empty"><p>학원 정보를 불러오지 못했습니다.</p><button className="button" onClick={() => setLoadAttempt((value) => value + 1)}>다시 시도</button></div>;
  return (
    <div className="academy-page">
      <div className="heading"><div><div className="eyebrow">ACADEMY SETTINGS</div><h1>{saved ? '우리 학원 정보 관리' : '우리 학원 정보를 알려주세요'}</h1><p>우선 받고 싶은 과목·학생의 현재 학년·수준과 전화 응대 시간을 알려주세요.</p></div></div>

      <form className="academy-layout" onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <div>
          <section className="academy-card"><div className="academy-section-head"><div><div className="academy-title"><span>01</span><h2>학원 기본 정보</h2></div><p className="academy-note">문의가 전달될 학원의 정보입니다.</p></div></div><div className="academy-fields">
            <label className="field">학원명 *<input placeholder="학원명을 입력하세요" required maxLength={80} value={profile.name} onChange={(e) => update({ name: e.target.value })} /></label>
            <label className="field">문의받을 전화번호 *<input type="tel" required maxLength={25} placeholder="053-000-0000" value={profile.phone} onChange={(e) => update({ phone: e.target.value })} /></label>
            <label className="field">지역 *<select aria-label="지역 *" required value={profile.region} onChange={(e) => update({ region: e.target.value })}><option value="">지역 선택</option>{options.regions.map((r) => <option key={r}>{r}</option>)}</select></label>
            <label className="field">상세 주소<input maxLength={160} value={profile.address} onChange={(e) => update({ address: e.target.value })} /></label>
          </div></section>
          <section className="academy-card"><div className="academy-section-head"><div><div className="academy-title"><span>02</span><h2>우선 받고 싶은 문의</h2></div><p className="academy-note">과목·현재 학년·수준의 일치도를 점수로 비교합니다. 수준은 선택하지 않아도 됩니다.</p></div><button className="button compact" type="button" disabled={profile.classes.length >= 50} onClick={() => update({ classes: [...profile.classes, { subject_code: 'MATH', grade_code: 'E1', level_code: null }] })}>＋ 선호 대상 추가</button></div>
            {!profile.classes.length ? <p className="academy-empty">선호 미설정 · 접수순으로 처리합니다.</p> : null}
            {profile.classes.map((p, index) => <div className="academy-row academy-preference-row" key={index}><div className="academy-row-head"><b>선호 대상 {index + 1}</b><button className="academy-remove" type="button" aria-label={`선호 대상 ${index + 1} 삭제`} onClick={() => update({ classes: profile.classes.filter((_, i) => i !== index) })}>×</button></div><div className="academy-preferences">
              <label className="field">과목<select value={p.subject_code} onChange={(e) => patchPreference(index, { subject_code: e.target.value })}>{options.subject.map((s) => <option key={s} value={s}>{fieldLabel('subject', s)}</option>)}</select></label>
              <label className="field">학교급<select value={p.grade_code[0]} onChange={(e) => patchPreference(index, { grade_code: e.target.value + '1' })}>{[['E', '초등학교'], ['M', '중학교'], ['H', '고등학교']].map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select></label>
              <label className="field">현재 학년<select value={p.grade_code} onChange={(e) => patchPreference(index, { grade_code: e.target.value })}>{options.grade.filter((g) => g[0] === p.grade_code[0]).map((g) => <option key={g} value={g}>{g.slice(1)}학년</option>)}</select></label>
              <label className="field">수준 · 선택<select value={p.level_code || ''} onChange={(e) => patchPreference(index, { level_code: e.target.value || null })}><option value="">선호 없음</option>{options.level.map((l) => <option key={l} value={l}>{levelLabel(l)}</option>)}</select></label>
            </div></div>)}
            <p className="academy-legend"><strong>설정하지 않아도 문의는 접수됩니다.</strong><br />선호 조건은 같은 학원의 문의 전달 순서에 참고하며, 실제 반 배정이나 등록 가능 여부를 확정하지 않습니다.</p>
          </section>
          <section className="academy-card"><div className="academy-section-head"><div><div className="academy-title"><span>03</span><h2>전화 응대 가능 시간</h2></div><p className="academy-note">수업시간과 별개로, 실제로 문의 전화를 받을 수 있는 시간을 선택해주세요.</p></div><button className="button compact" type="button" disabled={profile.windows.length >= 50} onClick={() => update({ windows: [...profile.windows, { days: [], start: '14:00', end: '18:00' }] })}>＋ 시간 추가</button></div>
            {profile.windows.map((window, index) => <fieldset className="academy-row academy-window" key={index}><legend className="sr-only">응대 시간 {index + 1}</legend><div className="academy-row-head"><div className="academy-days">{days.map((day, value) => <button type="button" className="button compact" key={day} aria-label={`시간 ${index + 1} ${day}요일`} aria-pressed={window.days.includes(value)} onClick={() => update({ windows: profile.windows.map((w, i) => i === index ? { ...w, days: w.days.includes(value) ? w.days.filter((d) => d !== value) : [...w.days, value].sort() } : w) })}>{day}</button>)}</div><button type="button" className="academy-remove" aria-label={`시간 ${index + 1} 삭제`} onClick={() => update({ windows: profile.windows.filter((_, i) => i !== index) })}>×</button></div><div className="academy-time">{(['start', 'end'] as const).map((key) => <label className="field" key={key}><span className="sr-only">{key === 'start' ? '시작' : '종료'}</span><input type="time" required value={window[key]} onChange={(e) => update({ windows: profile.windows.map((w, i) => i === index ? { ...w, [key]: e.target.value } : w) })} /></label>)}<span className="academy-time-zone">한국 시간</span></div></fieldset>)}
            <p className="academy-call-note">설정한 시간 안에서 최초 발신과 재발신을 진행하는 방안입니다.<br />재시도 간격이 지나도 응대 시간이 아니면 다음 가능한 시간으로 미룹니다.</p>
          </section>
          <section className="academy-card academy-simulation"><div className="academy-title"><span>04</span><h2>발신 순서 시뮬레이션</h2></div><p className="academy-note">같은 학원의 가상 문의입니다. 위 선호 조건을 바꾸면 아래 점수와 순서가 달라집니다.</p><div className="academy-weights">{['과목', '학년', '수준'].map((label, i) => <label className="field" key={label}>{label} 일치 점수<input type="number" min="0" max="100" step="0.5" value={weights[i]} onChange={(e) => setWeights(weights.map((w, j) => j === i ? Math.max(0, Math.min(100, Number(e.target.value))) : w))} /></label>)}</div><p className="academy-legend"><strong>시연용 배점</strong> · 세 조건은 각각 1점으로 시작합니다. 선호 대상이 여러 개면 한 대상에서 얻은 최고 일치 점수를 사용합니다.<br />최종 점수 = 일치 점수 + 대기 보정. 대기 보정은 예시 값을 직접 넣는 방식이며 실제 시간 계산·보정 주기는 미정입니다.</p><div className="academy-table"><table><thead><tr><th>발신 순서</th><th>문의 조건</th><th>일치 점수</th><th>대기 보정 (+)</th><th>최종 점수</th></tr></thead><tbody>{inquiries.map((q, rank) => <tr key={q.id}><td>{rank + 1}</td><td>{preferenceLabel(q)}<small>접수 {q.id + 1}번</small></td><td>{q.match}</td><td><input aria-label={`접수 ${q.id + 1}번 대기 보정`} type="number" min="0" max="100" step="0.5" value={bonuses[q.id]} onChange={(e) => setBonuses(bonuses.map((b, i) => i === q.id ? Math.max(0, Math.min(100, Number(e.target.value))) : b))} /></td><td className="academy-score">{q.score}</td></tr>)}</tbody></table></div><p className="academy-note">접수 1번 문의의 보정을 높여 장기 대기 문의의 순서가 달라지는 모습을 확인할 수 있습니다. 실제 발신은 하지 않습니다.</p></section>
          <p className="auth-error" role="alert">{error}</p><div className="academy-actions"><span className="muted">{dirty ? '저장하지 않은 변경 사항이 있습니다.' : saved?.updated_at ? `저장: ${new Date(saved.updated_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}` : '입력 내용을 확인하고 등록하세요.'}</span><button type="button" className="button" onClick={() => { const message = validateProfile(profile); setError(message); if (!message) dialog.current?.showModal(); }}>입력 내용 미리보기 →</button><button className="button primary" disabled={saving}>{saving ? '저장 중…' : saved ? '변경 사항 저장' : '학원 등록'}</button></div>
        </div>
        <aside className="academy-summary" aria-label="학원 정보 요약">
          <div className="academy-card">
            <div className="eyebrow">우리 학원 요약</div>
            <h2 className="academy-summary-name">{profile.name || '우리 학원'}</h2>
            <p className="academy-summary-sub">{profile.region || '지역을 입력해주세요'} {profile.address}</p>
            <div className="academy-counts"><div><b>{profile.classes.length}</b><span>선호 대상</span></div><div><b>{profile.windows.length}</b><span>응대 시간대</span></div></div>
            <section className="academy-summary-section"><h3>이런 학생의 문의를 우선 받아요</h3><div className="academy-chips">{profile.classes.map((p, i) => <span key={i} className="academy-chip">{preferenceLabel(p)}</span>)}{!profile.classes.length ? <span className="academy-chip neutral">선호 미설정 · 접수순</span> : null}</div></section>
            <section className="academy-summary-section"><h3>전화받기 편한 시간</h3>{profile.windows.map((w, i) => <p key={i} className="academy-schedule">{w.days.map((d) => days[d]).join('·') || '요일 미선택'} <span>{w.start}–{w.end}</span></p>)}</section>
            <section className="academy-summary-section"><h3>문의 전달 순서는 이렇게 검토해요</h3><ol className="academy-order"><li><strong>과목·학년·수준</strong>의 일치 점수 계산</li><li><strong>대기 보정 점수</strong>를 더해 최종 점수 산정</li><li><strong>높은 점수부터 발신</strong>, 동점은 접수순</li></ol><p className="academy-note">선호 미설정·동점은 접수순을 기본으로 합니다. 구체적인 배점과 대기 보정 주기는 검토 중입니다.</p></section>
            <section className="academy-summary-section"><p className="academy-note">실제 남은 자리와 수강 가능 여부는 <strong>전화 문의로 확인</strong>합니다.</p></section>
          </div>
          {mockMode ? <p className="academy-demo-note">미리보기 · 입력 정보는 이 브라우저에만 저장됩니다.</p> : null}
          <button type="button" className="academy-cancel" onClick={() => { if (!dirty || window.confirm('변경 내용을 취소하시겠어요?')) { setProfile(saved || emptyProfile()); setError(''); } }}>변경 취소</button>
        </aside>
      </form>
      <dialog className="academy-dialog" ref={dialog} aria-labelledby="academy-preview-title" aria-describedby="academy-preview-note">
        <div className="academy-preview-head"><div><div className="eyebrow">ACADEMY PREVIEW</div><h2 id="academy-preview-title">입력한 학원 정보</h2><p id="academy-preview-note">저장하기 전에 학원 정보와 응대 시간을 확인해 주세요.</p></div><button type="button" className="academy-remove" aria-label="미리보기 닫기" onClick={() => dialog.current?.close()}>×</button></div>
        <div className="academy-preview-body">
          <section className="academy-preview-identity"><span className="academy-preview-icon" aria-hidden="true">▱</span><div><h3>{profile.name}</h3><p>{profile.region} {profile.address}</p><a href={`tel:${profile.phone}`}>{profile.phone}</a></div><span className="academy-preview-badge">학원 정보</span></section>
          <section className="academy-preview-section"><div className="academy-preview-section-title"><h3><span>01</span> 우선 받고 싶은 문의</h3><span>{profile.classes.length}개 대상</span></div>{profile.classes.length ? <div className="academy-preview-preferences">{profile.classes.map((p, i) => <div className="academy-preview-preference" key={i}><span className="academy-preview-subject">{fieldLabel('subject', p.subject_code)}</span><span>{fieldLabel('grade', p.grade_code)}</span><span className="academy-chip">{p.level_code ? levelLabel(p.level_code) : '수준 무관'}</span></div>)}</div> : <p className="academy-empty">선호 미설정 · 접수순으로 처리합니다.</p>}</section>
          <section className="academy-preview-section"><div className="academy-preview-section-title"><h3><span>02</span> 전화 응대 가능 시간</h3><span>한국 시간 · KST</span></div><div className="academy-preview-schedules">{profile.windows.map((w, i) => <div className="academy-preview-schedule" key={i}><div className="academy-preview-days">{days.map((day, d) => <span key={day} className={w.days.includes(d) ? 'selected' : ''}>{day}</span>)}</div><strong>{w.start}<span>–</span>{w.end}</strong></div>)}</div></section>
          <p className="academy-call-note">선호 조건은 문의 전달 순서에 참고합니다. 실제 남은 자리와 수강 가능 여부는 전화 문의로 확인합니다.</p>
        </div>
        <div className="academy-preview-footer"><p>{mockMode ? '미리보기 · 이 브라우저에만 저장됩니다.' : '저장하면 우리 학원 정보에 반영됩니다.'}</p><div><button type="button" className="button" onClick={() => dialog.current?.close()}>돌아가서 수정</button><button type="button" className="button primary" disabled={saving} onClick={() => void save()}>{saving ? '저장 중…' : '확인 후 저장'}</button></div></div>
      </dialog>
    </div>
  );
}
