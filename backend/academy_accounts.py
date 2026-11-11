"""Session-owned academy registration and atomic profile/settings updates."""
import re
from datetime import time

from fastapi import HTTPException
from pydantic import Field, field_validator, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from contracts import AcademySettingsInput, REGIONS
from schema import accounts, academies, academy_profiles, academy_setting_states
from service import aware, uid


class AcademyProfileInput(AcademySettingsInput):
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=7, max_length=25)
    region: str
    address: str = Field(default='', max_length=160)

    @field_validator('name', 'phone', 'address')
    @classmethod
    def trim(cls, value):
        return value.strip()

    @field_validator('name')
    @classmethod
    def nonblank(cls, value):
        if not value:
            raise ValueError('Academy name required')
        return value

    @field_validator('phone')
    @classmethod
    def valid_phone(cls, value):
        if not re.fullmatch(r'[+\d()\s-]{7,25}', value) or len(re.sub(r'\D', '', value)) < 7:
            raise ValueError('Invalid phone number')
        return value

    @field_validator('region')
    @classmethod
    def valid_region(cls, value):
        if value not in REGIONS:
            raise ValueError('Unknown region')
        return value

    @model_validator(mode='after')
    def call_windows(self):
        if not self.call_hours:
            raise ValueError('Call hours required')
        windows = {}
        for window in self.call_hours:
            start, end = time.fromisoformat(window.start_time), time.fromisoformat(window.end_time)
            if start >= end:
                raise ValueError('Call hours must end after start')
            ranges = windows.setdefault(window.day_of_week, [])
            if any(first < end and start < last for first, last in ranges):
                raise ValueError('Overlapping call hours')
            ranges.append((start, end))
        return self


class AcademyProfileUpdate(AcademyProfileInput):
    version: int = Field(ge=1)


class AcademyAccounts:
    def __init__(self, service):
        self.service = service

    def _owner(self, connection, token):
        owner = self.service.owner(connection, token)
        account_type = connection.execute(select(accounts.c.account_type).where(accounts.c.user_id == owner)).scalar()
        if account_type != 'academy':
            raise HTTPException(403, 'Academy account required')
        return owner

    def _read(self, connection, owner):
        row = connection.execute(select(academies, academy_profiles.c.address,
                                        academy_setting_states.c.version,
                                        academy_setting_states.c.last_modified_at)
            .join(academy_profiles, academy_profiles.c.academy_id == academies.c.id)
            .join(academy_setting_states, academy_setting_states.c.academy_id == academies.c.id)
            .where(academy_profiles.c.owner_id == owner)).mappings().first()
        if row is None:
            raise HTTPException(404, 'Academy not registered')
        settings = self.service.read_academy_settings(connection, row['id'])
        return aware(dict(academy_id=row['id'], name=row['name'], phone=row['phone'],
                          region=row['region'], address=row['address'], version=row['version'],
                          updated_at=row['last_modified_at'], **settings))

    def get(self, token):
        with self.service.engine.connect() as connection:
            return self._read(connection, self._owner(connection, token))

    def save(self, token, body, *, create):
        with self.service.engine.begin() as connection:
            self.service.lock(connection)
            owner = self._owner(connection, token)
            academy_id = connection.execute(select(academy_profiles.c.academy_id).where(
                academy_profiles.c.owner_id == owner)).scalar()
            if create:
                if academy_id:
                    raise HTTPException(409, 'Academy already registered')
                academy_id = uid()
                # New profiles use the existing real-call eligibility checks.
                connection.execute(academies.insert().values(
                    id=academy_id, name=body.name, phone=body.phone, region=body.region,
                    is_mock=False, hours=[dict(weekday=day, start_minute=0, end_minute=1440) for day in range(7)]))
                try:
                    connection.execute(academy_profiles.insert().values(
                        academy_id=academy_id, owner_id=owner, address=body.address))
                except IntegrityError:
                    raise HTTPException(409, 'Academy already registered') from None
            else:
                if academy_id is None:
                    raise HTTPException(404, 'Academy not registered')
                version = connection.execute(select(academy_setting_states.c.version).where(
                    academy_setting_states.c.academy_id == academy_id)).scalar()
                if body.version != version:
                    raise HTTPException(409, 'Academy was modified; reload before saving')
                connection.execute(update(academies).where(academies.c.id == academy_id).values(
                    name=body.name, phone=body.phone, region=body.region))
                connection.execute(update(academy_profiles).where(
                    academy_profiles.c.academy_id == academy_id).values(address=body.address))
            self.service.write_academy_settings(connection, academy_id, body)
            return self._read(connection, owner)
