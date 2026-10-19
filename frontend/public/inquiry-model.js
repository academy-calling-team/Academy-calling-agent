export const states = { queued:'처리 대기', calling:'통화 중', retry_wait:'재시도 대기', completed:'상담 완료', failed:'처리 실패' };
export const active = status => ['queued','calling','retry_wait'].includes(status);
export const reasons = { unknown:'학원에서 답변을 확인하지 못했습니다.', refused:'학원에서 답변을 거절했습니다.', not_asked:'이 질문을 아직 묻지 못했습니다.' };
export const failureReasons = { real_test_disabled:'실통화 시험이 비활성화되어 발신하지 않았습니다.', retry_exhausted:'연락 시도 한도에 도달했습니다. 실통화 시험은 자동 재발신하지 않습니다.', no_answer:'학원에서 전화를 받지 않았습니다.', busy:'학원이 통화 중입니다.', rejected:'학원에서 통화를 거절했습니다.', machine:'자동 응답으로 연결되었습니다.', invalid_number:'학원 전화번호를 확인해야 합니다.', disclosure_missing:'상담 안내가 확인되지 않아 중단되었습니다.', delivery_or_result_timeout:'통화 연결 또는 결과 확인 시간이 초과되었습니다.' };
export function fieldLabel(kind, code) {
  if(kind==='grade' && /^[EMH]\d$/.test(code)) return `${{E:'초등학교',M:'중학교',H:'고등학교'}[code[0]]} ${code.slice(1)}학년`;
  return ({subject:{KOR:'국어',ENG:'영어',MATH:'수학',SCI:'과학',SOC:'사회'},level:{HIGH:'상급',MID:'중급',LOW:'기초'}}[kind]||{})[code]||code;
}
export function answerView(answer) {
  if(answer?.answered !== true) return { kind:'unknown', label:'미확인', reason:reasons[answer?.reason]||'확인된 답변이 없습니다.', detail:answer?.detail||'' };
  if(answer.question_code==='class_time') return {kind:'time',label:'시간 확인',reason:'',detail:answer.detail||''};
  if(answer.yes_no===false) return {kind:'no',label:'불가',reason:'',detail:answer.detail||''};
  if(answer.yes_no===true) return {kind:'yes',label:'가능',reason:'',detail:answer.detail||''};
  return {kind:'unknown',label:'미확인',reason:'답변을 추가로 확인해야 합니다.',detail:answer.detail||''};
}
export function inquiryPayload(form) {
  return { academy_id:form.academy_id, student:{grade:form.grade,subject:form.subject,level:form.level,region:form.region}, question_codes:[...form.question_codes] };
}
export function submissionKey(previous, payload, random = () => crypto.randomUUID()) {
  const fingerprint=JSON.stringify(payload);
  return previous?.fingerprint===fingerprint ? previous : {fingerprint,key:random()};
}
