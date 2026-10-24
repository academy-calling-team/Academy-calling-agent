import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useCatalog } from '../hooks/useInquiries';
import { useToast } from '../hooks/useToast';
import { api, getSessionEpoch } from '../lib/api';
import { ErrorPanel, Head, Loading } from '../components/ui';
import {
  fieldLabel,
  inquiryPayload,
  submissionKey,
  type FormValues,
  type SubmissionKey,
} from '../lib/inquiry-model';
import { clearPending, readPending, writePending } from '../lib/pending';

export default function NewInquiryPage() {
  const { user, mockMode, ready } = useAuth();
  const catalog = useCatalog(ready);
  const toast = useToast();
  const navigate = useNavigate();

  const [formValues, setFormValues] = useState<FormValues>({
    academy_id: '',
    grade: '',
    subject: '',
    level: '',
    region: '',
    question_codes: [],
    real_test_confirm: false,
  });
  const [pending, setPending] = useState<SubmissionKey | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const pendingRestored = useRef(false);

  useEffect(() => {
    if (pendingRestored.current || !user) return;
    pendingRestored.current = true;
    const stored = readPending(user.displayName, mockMode ? 'mock' : 'backend');
    if (!stored) return;
    try {
      const payload = JSON.parse(stored.fingerprint) as {
        academy_id: string;
        student: Omit<FormValues, 'academy_id' | 'question_codes' | 'real_test_confirm'>;
        question_codes: string[];
      };
      setPending({ fingerprint: stored.fingerprint, key: stored.key });
      setFormValues({
        academy_id: payload.academy_id,
        grade: payload.student.grade,
        subject: payload.student.subject,
        level: payload.student.level,
        region: payload.student.region,
        question_codes: payload.question_codes,
        real_test_confirm: false,
      });
    } catch {
      /* ignore */
    }
  }, [user, mockMode]);

  const selectedAcademy = useMemo(
    () => catalog.academies.find((a) => a.academy_id === formValues.academy_id),
    [catalog.academies, formValues.academy_id],
  );
  const isRealTest = selectedAcademy?.is_mock === false;

  function update(patch: Partial<FormValues>) {
    setFormValues((prev) => ({ ...prev, ...patch }));
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (submitting) return;
    setError('');
    if (!formValues.question_codes.length) {
      setError('문의 항목을 한 가지 이상 선택해 주세요.');
      return;
    }
    if (selectedAcademy?.can_submit === false) {
      setError(selectedAcademy.notice || '실통화 시험 준비가 완료되지 않았습니다.');
      return;
    }
    if (isRealTest && !formValues.real_test_confirm) {
      setError('수신자 준비와 실제 전화 요청을 확인해 주세요.');
      return;
    }
    const options = catalog.options;
    const payload = inquiryPayload(formValues);
    if (
      !options ||
      !catalog.academies.some((a) => a.academy_id === payload.academy_id) ||
      !['grade', 'subject', 'level'].every((k) => {
        const key = k as 'grade' | 'subject' | 'level';
        const list = options[key];
        return list.includes(payload.student[key]);
      }) ||
      !options.regions.includes(payload.student.region) ||
      !payload.question_codes.every((c) => c in options.question_codes)
    ) {
      setError('선택한 정보를 다시 확인해 주세요.');
      return;
    }

    const keyState = submissionKey(pending, payload);
    setPending(keyState);
    if (user) writePending(user.displayName, mockMode ? 'mock' : 'backend', keyState);

    const epoch = getSessionEpoch();
    setSubmitting(true);
    try {
      const result = await api<{ inquiry_id: string; status: string; duplicate?: boolean }>('/api/inquiries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': keyState.key },
        body: JSON.stringify(payload),
      });
      if (epoch !== getSessionEpoch()) return;
      clearPending();
      setPending(null);
      setSubmitting(false);
      toast.show(result.duplicate ? '이미 접수된 상담을 확인합니다.' : '상담이 접수되었습니다.');
      navigate(`/detail/${encodeURIComponent(result.inquiry_id)}`);
    } catch (err) {
      if (epoch !== getSessionEpoch()) return;
      setSubmitting(false);
      const message = (err as Error).message;
      setError(
        (err as { status?: number }).status === 409
          ? message
          : message + ' 같은 내용으로 다시 시도하면 중복 접수를 방지합니다.',
      );
    }
  }

  function toggleQuestion(code: string) {
    setFormValues((prev) => ({
      ...prev,
      question_codes: prev.question_codes.includes(code)
        ? prev.question_codes.filter((c) => c !== code)
        : [...prev.question_codes, code],
    }));
  }

  if (!ready || catalog.state === 'loading' || catalog.state === 'idle') {
    return (
      <>
        <Head title="새 상담" desc="학원과 문의 항목을 준비하고 있습니다." />
        <Loading />
      </>
    );
  }
  if (catalog.state === 'error') {
    return (
      <>
        <Head title="새 상담" desc="상담할 학원과 문의 항목을 확인해 주세요." />
        <ErrorPanel message={catalog.error} onAction={() => void catalog.reload()} />
      </>
    );
  }
  if (!catalog.academies.length) {
    return (
      <>
        <Head title="새 상담" desc="상담할 학원을 확인해 주세요." />
        <ErrorPanel message="현재 선택할 수 있는 학원이 없습니다." onAction={() => void catalog.reload()} />
      </>
    );
  }

  const options = catalog.options!;

  return (
    <>
      <Head title="어떤 점이 궁금하세요?" desc="학원, 학생 조건과 질문을 선택해 상담을 접수하세요." />
      <form className="form-grid" aria-busy={submitting} onSubmit={onSubmit}>
        <div className="panel">
          <fieldset disabled={submitting}>
            <section className="form-section">
              <h2>01 학원 선택</h2>
              <label className="field">
                상담할 학원
                <select
                  name="academy_id"
                  required
                  value={formValues.academy_id}
                  onChange={(e) => update({ academy_id: e.target.value })}
                >
                  <option value="">선택해 주세요</option>
                  {catalog.academies.map((a) => (
                    <option key={a.academy_id} value={a.academy_id}>
                      {a.name} · {a.region}
                      {a.is_test
                        ? a.can_submit
                          ? ' · 실제 전화 1회'
                          : ' · 시험 준비 중'
                        : ' · 목업'}
                    </option>
                  ))}
                </select>
              </label>
            </section>
            <section className="form-section">
              <h2>02 학생 정보</h2>
              <div className="fields">
                <label className="field">
                  학년
                  <select name="grade" required value={formValues.grade} onChange={(e) => update({ grade: e.target.value })}>
                    <option value="">선택해 주세요</option>
                    {options.grade.map((g) => (
                      <option key={g} value={g}>
                        {fieldLabel('grade', g)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  과목
                  <select name="subject" required value={formValues.subject} onChange={(e) => update({ subject: e.target.value })}>
                    <option value="">선택해 주세요</option>
                    {options.subject.map((s) => (
                      <option key={s} value={s}>
                        {fieldLabel('subject', s)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  현재 학습 수준
                  <select name="level" required value={formValues.level} onChange={(e) => update({ level: e.target.value })}>
                    <option value="">선택해 주세요</option>
                    {options.level.map((l) => (
                      <option key={l} value={l}>
                        {fieldLabel('level', l)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  지역
                  <select name="region" required value={formValues.region} onChange={(e) => update({ region: e.target.value })}>
                    <option value="">선택해 주세요</option>
                    {options.regions.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </section>
            <section className="form-section">
              <h2>03 문의 항목</h2>
              <p>한 가지 이상 선택하세요.</p>
              <div className="choices">
                {Object.entries(options.question_codes).map(([code, label]) => (
                  <label className="choice" key={code}>
                    <input
                      type="checkbox"
                      name="codes"
                      value={code}
                      checked={formValues.question_codes.includes(code)}
                      onChange={() => toggleQuestion(code)}
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
            </section>
          </fieldset>
        </div>
        <aside className="panel summary">
          <div className="eyebrow">YOUR INQUIRY</div>
          <h2>상담 내용</h2>
          <dl>
            <dt>상담할 학원</dt>
            <dd id="school-summary">{selectedAcademy?.name || '학원을 선택하세요'}</dd>
            <dt>선택한 항목</dt>
            <dd id="count-summary">
              {formValues.question_codes.length ? `${formValues.question_codes.length}개` : '질문을 선택하세요'}
            </dd>
            <dt>상담 방식</dt>
            <dd>AI 전화 상담</dd>
          </dl>
          {isRealTest ? (
            <section id="real-test-notice">
              <p id="real-test-message" className="notice">
                {selectedAcademy?.notice || '실제 전화 시험 대상입니다.'}
              </p>
              <label className="consent">
                <input
                  name="real_test_confirm"
                  type="checkbox"
                  checked={Boolean(formValues.real_test_confirm)}
                  disabled={selectedAcademy?.can_submit === false || submitting}
                  onChange={(e) => update({ real_test_confirm: e.target.checked })}
                />
                <span>시험 수신자가 지금 전화를 받을 준비가 되었고 실제 전화 1회를 요청함을 확인합니다.</span>
              </label>
            </section>
          ) : null}
          <p id="error" className="auth-error" role="alert">
            {error}
          </p>
          <button className="button primary" type="submit" disabled={submitting || selectedAcademy?.can_submit === false}>
            {submitting ? '접수 중…' : '상담 접수 ↗'}
          </button>
          <p className="summary-note">
            {mockMode
              ? '격리된 미리보기 데이터로만 접수됩니다. 실제 요청은 전송되지 않습니다.'
              : '접수 후 학원 운영 시간에 맞춰 처리합니다. 일반 학원은 목업으로 처리하며, 실통화 시험용 학원은 준비 확인 후 실제 전화 1회만 발신합니다.'}
          </p>
        </aside>
      </form>
    </>
  );
}
