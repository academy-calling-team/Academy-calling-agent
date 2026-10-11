from datetime import datetime
from typing import Literal
from pydantic import Field,SecretStr,field_validator,model_validator
from contracts import StrictModel,EventInput

class Credentials(StrictModel):
    login_name:str=Field(min_length=3,max_length=32,pattern=r'^[a-z][a-z0-9_]+$')
    password:SecretStr
    @field_validator('password')
    @classmethod
    def length(cls,value):
        if not 12<=len(value.get_secret_value())<=128:raise ValueError('Password length must be 12-128')
        return value
class CallbackReview(StrictModel):
    action:Literal['schedule','cancel']
    callback_at:datetime|None=None
    reason:str=Field(min_length=1,max_length=1000)
    @field_validator('callback_at',mode='before')
    @classmethod
    def when(cls,value):return None if value is None else EventInput.timestamp(value)
    @model_validator(mode='after')
    def coherent(self):
        if not self.reason.strip():raise ValueError('Review reason required')
        if (self.action=='schedule')!=(self.callback_at is not None):raise ValueError('Only schedule requires explicit time')
        return self
class FallbackReview(StrictModel):
    action:Literal['prepare','dismiss']
    reason:str=Field(min_length=1,max_length=1000)
    message:str|None=Field(None,max_length=1000)
    @model_validator(mode='after')
    def coherent(self):
        if not self.reason.strip():raise ValueError('Review reason required')
        if self.action=='prepare' and (not self.message or not self.message.strip()):raise ValueError('Message required')
        if self.action=='dismiss' and self.message is not None:raise ValueError('Dismiss does not send a message')
        return self
