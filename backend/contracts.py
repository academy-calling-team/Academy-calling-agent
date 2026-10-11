from datetime import datetime,date
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator

QUESTION_LABELS = {'shuttle':'통학 차량', 'pickup':'픽업', 'level_fit':'수준에 맞는 반',
                   'vacancy':'남은 자리', 'level_test':'레벨 테스트', 'class_time':'수업 요일·시간'}
REGIONS = ['대구 북구 침산동', '대구 북구 태전동', '대구 수성구 범어동']
QuestionCode = Literal['shuttle','pickup','level_fit','vacancy','level_test','class_time']
Outcome = Literal['answered','no_answer','busy','rejected','machine','invalid_number']
class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
class Student(StrictModel):
    grade: str = Field(pattern=r'^(E[1-6]|M[1-3]|H[1-3])$')
    subject: Literal['KOR','ENG','MATH','SCI','SOC']
    level: Literal['HIGH','MID','LOW']
    region: str
    @field_validator('region')
    @classmethod
    def region_selected(cls, value):
        if value not in REGIONS:
            raise ValueError('Select a mock region from /api/options')
        return value
class InquiryInput(StrictModel):
    inquirer_id: str = Field(min_length=1, max_length=36)
    academy_id: str = Field(min_length=1, max_length=36)
    student: Student
    question_codes: list[QuestionCode] = Field(min_length=1, max_length=6)
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.question_codes)) != len(self.question_codes):
            raise ValueError('Duplicate question codes')
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
class AnswerInput(StrictModel):
    question_id: str = Field(min_length=1, max_length=36)
    question_code: QuestionCode
    asked: bool
    answered: bool
    yes_no: bool | None
    reason: Literal['unknown','refused','not_asked'] | None = None
    detail: str = Field(max_length=2000)
    @model_validator(mode='after')
    def coherent(self):
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
        if self.outcome != 'answered':
            if self.consult_accepted is not None or self.available_times or self.latency is not None:
                raise ValueError('Non-human connection must not contain consultation or latency')
            if self.disclosure_played is not None or any(a.asked for a in self.answers) or self.transcript:
                raise ValueError('Non-human connection has no dialogue or disclosure measurement')
        if self.callback_requested:
            if self.outcome != 'answered':
                raise ValueError('Callback requires human answer')
        elif self.callback_at is not None:
            raise ValueError('callback_at requires callback_requested')
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
