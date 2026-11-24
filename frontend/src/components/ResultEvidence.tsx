import type { ResultEvidence as Evidence } from '../lib/inquiry-model';

export function ResultEvidence({ value }: { value?: Evidence | null }) {
  const turns = (value?.evidence_dialogue || []).filter((turn) => turn.text?.trim())
    .slice().sort((a, b) => a.turn_no - b.turn_no);
  if (turns.length) {
    return (
      <section className="answer-source evidence-dialogue" aria-label="근거 대화">
        <h4>근거 대화</h4>
        <ol>{turns.map((turn, index) => (
          <li key={`${turn.turn_no}-${index}`}>
            <span className="evidence-speaker">{turn.speaker === 'agent' ? 'AI 상담원' : turn.speaker === 'academy' ? '학원' : '발화자'}</span>
            <blockquote>{turn.text}</blockquote>
          </li>
        ))}</ol>
      </section>
    );
  }
  return value?.source_text?.trim() ? (
    <section className="answer-source" aria-label="학원 발화 원문">
      <h4>학원 발화 원문</h4>
      <blockquote>{value.source_text}</blockquote>
    </section>
  ) : null;
}
