from datetime import datetime,date,time
from typing import Annotated, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator

QUESTION_LABELS = {'shuttle':'통학 차량', 'pickup':'픽업', 'level_fit':'수준에 맞는 반',
                   'vacancy':'남은 자리', 'level_test':'레벨 테스트', 'class_time':'수업 요일·시간'}
CALL_STATUS_LABELS_KR = {
    'reserved':'발신 대기', 'delivery_unknown':'요청 전달 확인 중', 'accepted':'발신 요청 접수',
    'initiated':'발신 시작', 'ringing':'호출 중', 'answered':'통화 중',
    'ended':'통화 종료·결과 대기', 'finished':'통화 종료', 'timeout':'시간 초과',
}
CALL_OUTCOME_LABELS_KR = {
    'answered':'연결됨', 'no_answer':'부재중', 'busy':'통화 중',
    'rejected':'수신 거절', 'machine':'자동 응답', 'invalid_number':'전화번호 오류',
}
REGIONS = ['대구 북구 침산동', '대구 북구 태전동', '대구 수성구 범어동']
QuestionCode = Literal['shuttle','pickup','level_fit','vacancy','level_test','class_time']
LocationQuestionCode = Literal['shuttle', 'pickup']
LocationKind = Literal['집 근처', '학교', '다른 학원']
Outcome = Literal['answered','no_answer','busy','rejected','machine','invalid_number']
AnswerReason = Literal['unknown', 'refused', 'not_asked', 'uncertain', 'redirect']
TurnNumber = Annotated[int, Field(ge=0, strict=True)]
ConditionText = Annotated[str, Field(min_length=1, max_length=200)]
ReasonText = Annotated[str, Field(min_length=1, max_length=500)]
SourceText = Annotated[str, Field(min_length=1, max_length=2000)]
EvidenceTurns = Annotated[list[TurnNumber], Field(max_length=10)]
EndReason = Literal['completed', 'academy_hung_up', 'connection_lost', 'agent_error']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class QuestionLocation(StrictModel):
    kind: LocationKind
    name: str = Field(min_length=1, max_length=100)
    @field_validator('name')
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError('Location name must not be blank')
        return value.strip()

class Student(StrictModel):
    grade: str = Field(pattern=r'^(E[1-6]|M[1-3]|H[1-3])$')
    subject: Literal['KOR','ENG','MATH','SCI','SOC']
    level: Literal['HIGH','MID','LOW']
    region: str | None = None
    @field_validator('region')
    @classmethod
    def region_selected(cls, value):
        if value is not None and value not in REGIONS:
            raise ValueError('Select a mock region from /api/options')
        return value

class InquiryInput(StrictModel):
    inquirer_id: str = Field(min_length=1, max_length=36)
    academy_id: str = Field(min_length=1, max_length=36)
    student: Student
    question_codes: list[QuestionCode] = Field(min_length=1, max_length=6)
    locations: dict[LocationQuestionCode, QuestionLocation] | None = None
    @model_validator(mode='after')
    def unique_and_valid_locations(self):
        if len(set(self.question_codes)) != len(self.question_codes):
            raise ValueError('Duplicate question codes')
        if self.locations:
            unknown_keys = set(self.locations.keys()) - set(self.question_codes)
            if unknown_keys:
                raise ValueError('Location provided for unrequested question code')
        return self

class EventInput(StrictModel):
    event_id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    type: Literal['initiated','ringing','answered','no_answer','busy','rejected','machine',
                  'invalid_number','completed','barge_in']
    occurred_at: datetime
    @field_validator('occurred_at', mode='before')
    @classmethod
    def timestamp(cls, value):
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace('Z','+00:00'))
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Timezone required')
        return value
class AnswerDetail(StrictModel):
    """Optional explanation shared by question answers and the fixed consultation check."""
    reason: AnswerReason | None = None
    condition: ConditionText | None = None
    reason_text: ReasonText | None = None
    source_text: SourceText | None = None
    evidence_turns: EvidenceTurns | None = None

    @field_validator('condition', 'reason_text', 'source_text')
    @classmethod
    def nonblank_explanation(cls, value):
        if value is not None and not value.strip():
            raise ValueError('Explanation must not be blank')
        return value

    @field_validator('evidence_turns')
    @classmethod
    def unique_evidence(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError('Duplicate evidence turn numbers')
        return value

class AnswerInput(AnswerDetail):
    question_id: str = Field(min_length=1, max_length=36)
    question_code: QuestionCode
    asked: bool
    answered: bool
    yes_no: bool | None
    detail: str = Field(max_length=2000)

    @model_validator(mode='after')
    def coherent(self):
        if self.source_text is not None and (not self.asked or not self.source_text.strip()):
            raise ValueError('Source text requires an asked question and a nonblank excerpt')
        if self.condition is not None and not (self.answered and self.yes_no is True):
            raise ValueError('Condition requires answered=true and yes_no=true')
        if self.evidence_turns and not self.asked:
            raise ValueError('Unasked question must not reference dialogue evidence')
        if self.answered:
            if not self.asked or self.reason is not None or not self.detail.strip():
                raise ValueError('Answered requires asked, detail and no reason')
            if self.question_code == 'class_time' and self.yes_no is not None:
                raise ValueError('class_time uses detail and yes_no=null')
            if self.question_code != 'class_time' and self.yes_no is None:
                raise ValueError('Binary answer requires yes_no')
        else:
            if self.yes_no is not None or self.reason is None:
                raise ValueError('Missing answer requires reason and yes_no=null')
            if (not self.asked) != (self.reason == 'not_asked'):
                raise ValueError('not_asked reason must match asked=false')
        return self
class Latency(StrictModel):
    mean_ms: int = Field(ge=0)
    p95_ms: int = Field(ge=0)
    turns: int = Field(ge=1)
class TranscriptTurn(StrictModel):
    speaker: Literal['agent','academy']
    at_ms: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=4000)
    turn_no: TurnNumber | None = None
class ResultInput(StrictModel):
    result_id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    outcome: Outcome
    disclosure_played: bool | None
    consult_accepted: bool | None
    available_times: list[str] = Field(max_length=20)
    answers: list[AnswerInput] = Field(max_length=6)
    unresolved: list[str] = Field(max_length=6)
    summary_text: str = Field(max_length=2000)
    notes: str = Field(default='', max_length=1000)
    latency: Latency | None
    duration_sec: int = Field(ge=0, le=86400)
    transcript: list[TranscriptTurn] = Field(max_length=1000)
    recording_url: str | None = Field(default=None, max_length=2000)
    callback_requested: bool = False
    callback_at: datetime | None = None
    rejection_reason: Literal['temporary','permanent','unknown'] | None = None
    consult: AnswerDetail | None = None
    callback_reason_text: ReasonText | None = None
    callback_source_text: ReasonText | None = None
    end_reason: EndReason | None = None
    @field_validator('callback_reason_text', 'callback_source_text')
    @classmethod
    def nonblank_callback_text(cls, value):
        if value is not None and not value.strip():
            raise ValueError('Callback text must not be blank')
        return value
    @field_validator('callback_at', mode='before')
    @classmethod
    def timestamp(cls, value):
        return None if value is None else EventInput.timestamp(value)
    @model_validator(mode='after')
    def coherent(self):
        qids = [a.question_id for a in self.answers]
        if len(qids) != len(set(qids)):
            raise ValueError('Duplicate answers')
        missing = {a.question_id for a in self.answers if not a.answered}
        if len(set(self.unresolved)) != len(self.unresolved) or set(self.unresolved) != missing:
            raise ValueError('unresolved must match missing answers exactly')
        if self.available_times and self.consult_accepted is not True:
            raise ValueError('Available times require consultation acceptance')
        if self.consult is not None:
            if self.consult_accepted is None:
                if self.consult.reason is None:
                    raise ValueError('Unconfirmed consultation requires a reason')
            elif self.consult.reason is not None:
                raise ValueError('Confirmed consultation must not have a missing-answer reason')
            if self.consult.condition is not None and self.consult_accepted is not True:
                raise ValueError('Consultation condition requires acceptance')
            if self.consult.reason == 'not_asked' and (self.consult.source_text is not None or self.consult.evidence_turns):
                raise ValueError('Unasked consultation must not contain dialogue evidence')
        turn_numbers = [turn.turn_no for turn in self.transcript if turn.turn_no is not None]
        if len(turn_numbers) != len(set(turn_numbers)):
            raise ValueError('Duplicate transcript turn numbers')
        known_turns = set(turn_numbers)
        for explanation in [*self.answers, *([self.consult] if self.consult is not None else [])]:
            if not set(explanation.evidence_turns or []).issubset(known_turns):
                raise ValueError('Evidence must reference explicitly numbered turns in this result')
        if self.outcome != 'answered':
            if self.consult_accepted is not None or self.available_times or self.latency is not None:
                raise ValueError('Non-human connection must not contain consultation or latency')
            if self.disclosure_played is not None or any(a.asked for a in self.answers) or self.transcript:
                raise ValueError('Non-human connection has no dialogue or disclosure measurement')
            if self.consult is not None or self.end_reason is not None:
                raise ValueError('Consultation detail and end_reason require human answer')
        if self.callback_requested:
            if self.outcome != 'answered':
                raise ValueError('Callback requires human answer')
        elif self.callback_at is not None:
            raise ValueError('callback_at requires callback_requested')
        if not self.callback_requested and (self.callback_reason_text is not None or self.callback_source_text is not None):
            raise ValueError('Callback explanation requires callback_requested')
        if self.rejection_reason is not None and self.outcome != 'rejected':
            raise ValueError('Rejection reason only applies to rejected')
        return self

# Review is a local service operation; no public or voice-worker correction endpoint.
class CorrectionInput(StrictModel):
    base_revision: int = Field(ge=0)
    reviewer: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)
    payload: ResultInput
    @field_validator('reviewer','reason')
    @classmethod
    def nonblank(cls,value):
        if not value.strip(): raise ValueError('Review metadata must not be blank')
        return value.strip()

class OpeningWindow(StrictModel):
    weekday: int = Field(ge=0,le=6)
    start_minute: int = Field(ge=0,lt=1440)
    end_minute: int = Field(ge=0,le=1440)
    @model_validator(mode='after')
    def nonempty(self):
        if self.start_minute==self.end_minute: raise ValueError('Empty time window')
        return self
class AcademyPolicyInput(StrictModel):
    enabled: bool
    max_concurrent: int = Field(ge=1,le=10)
    cooldown_seconds: int = Field(ge=0,le=86400)
    closed_dates: list[str] = Field(max_length=366)
    hours: list[OpeningWindow] = Field(max_length=50)
    @field_validator('closed_dates')
    @classmethod
    def dates(cls,value):
        if len(value)!=len(set(value)): raise ValueError('Duplicate closure date')
        for item in value:
            if date.fromisoformat(item).isoformat()!=item: raise ValueError('YYYY-MM-DD required')
        return value

class AcademyClassInput(StrictModel):
    grade_code: str = Field(pattern=r'^(E[1-6]|M[1-3]|H[1-3])$')
    subject_code: Literal['KOR','ENG','MATH','SCI','SOC']
    level_code: Literal['HIGH','MID','LOW'] | None = None

class CallHourInput(StrictModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=r'^\d{2}:\d{2}(:\d{2})?$')
    end_time: str = Field(pattern=r'^\d{2}:\d{2}(:\d{2})?$')

    @model_validator(mode='after')
    def validate_window(self):
        if time.fromisoformat(self.start_time) == time.fromisoformat(self.end_time):
            raise ValueError('Call hours must have different start and end times')
        return self

class AcademySettingsInput(StrictModel):
    classes: list[AcademyClassInput] = Field(max_length=50)
    call_hours: list[CallHourInput] = Field(max_length=50)

    @model_validator(mode='after')
    def unique_classes(self):
        keys = {(row.grade_code, row.subject_code, row.level_code) for row in self.classes}
        if len(keys) != len(self.classes):
            raise ValueError('Duplicate academy class combination')
        return self
