export function Loading({ text = '불러오는 중…' }: { text?: string }) {
  return (
    <div className="empty loading" role="status">
      <span className="spinner" aria-hidden="true" />
      <p>{text}</p>
    </div>
  );
}

export function ErrorPanel({
  message,
  actionLabel = '다시 시도',
  onAction,
}: {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="empty error-panel" role="alert">
      <h3>정보를 불러올 수 없어요</h3>
      <p>{message}</p>
      <button className="button" type="button" onClick={onAction}>
        {actionLabel}
      </button>
    </div>
  );
}

export function Head({
  title,
  desc,
  action,
}: {
  title: React.ReactNode;
  desc: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="heading">
      <div>
        <div className="eyebrow">HAKWON AI · CONSULTATION</div>
        <h1>{title}</h1>
        <p>{desc}</p>
      </div>
      {action}
    </div>
  );
}

export function PrimaryLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <a className="button primary" href={to.startsWith('/') ? `#${to}` : to}>
      {children}
    </a>
  );
}

export function StatusBadge({
  status,
  reviewRequired,
  states,
}: {
  status: string;
  reviewRequired?: boolean;
  states: Record<string, string>;
}) {
  return (
    <>
      <span className={`badge ${status}`}>{states[status] || '상태 확인 필요'}</span>
      {reviewRequired ? <span className="badge review">확인 필요</span> : null}
    </>
  );
}
