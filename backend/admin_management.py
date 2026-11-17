"""Administrator-only catalog editing and explicit, single-target DB cleanup."""
import hashlib
import json
import logging
from datetime import time

from fastapi import HTTPException
from pydantic import Field, field_validator, model_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import DBAPIError

import schema as s
from academy_accounts import AcademyProfileInput
from contracts import AcademyClassInput, CallHourInput, StrictModel
from service import aware, uid


class AcademyEdit(StrictModel):
    model_config = {'json_schema_extra': {'examples': [
        {'version': 0, 'name': '시연 학원', 'phone': '010-0000-0001'},
        {'version': 1, 'call_hours': [{'day_of_week': 0, 'start_time': '14:00', 'end_time': '18:00'}]},
    ]}}
    version: int = Field(ge=0, description='조회 응답의 version. 기존 설정 기록이 없으면 0.')
    name: str | None = Field(default=None, min_length=1, max_length=80)
    phone: str | None = Field(default=None, max_length=25)
    region: str | None = None
    address: str | None = Field(default=None, max_length=160)
    classes: list[AcademyClassInput] | None = Field(default=None, max_length=50)
    call_hours: list[CallHourInput] | None = Field(default=None, min_length=1, max_length=50)

    @field_validator('name', 'phone', 'region', 'address')
    @classmethod
    def text(cls, value, info):
        if value is None:
            return value
        value = value.strip()
        if info.field_name == 'name':
            return AcademyProfileInput.nonblank(value)
        if info.field_name == 'phone':
            return AcademyProfileInput.valid_phone(value)
        if info.field_name == 'region':
            return AcademyProfileInput.valid_region(value)
        return value

    @model_validator(mode='after')
    def editable(self):
        fields = self.model_fields_set - {'version'}
        if not fields:
            raise ValueError('수정할 항목을 하나 이상 지정해 주세요.')
        if any(getattr(self, key) is None for key in fields - {'phone'}):
            raise ValueError('전화번호 이외의 수정 항목에는 null을 사용할 수 없습니다.')
        if self.classes is not None:
            keys = {(r.grade_code, r.subject_code, r.level_code) for r in self.classes}
            if len(keys) != len(self.classes):
                raise ValueError('운영 반이 중복되었습니다.')
        windows = {}
        for row in self.call_hours or []:
            start, end = time.fromisoformat(row.start_time), time.fromisoformat(row.end_time)
            if start >= end:
                raise ValueError('응대 종료 시각은 시작 시각보다 늦어야 합니다.')
            day = windows.setdefault(row.day_of_week, [])
            if any(a < end and start < b for a, b in day):
                raise ValueError('응대 시간이 겹칩니다.')
            day.append((start, end))
        return self


class DeleteConfirmation(StrictModel):
    confirm_id: str = Field(min_length=1, max_length=36, description='삭제할 대상의 정확한 ID')
    preview_token: str = Field(pattern=r'^[0-9a-f]{64}$', description='삭제 미리보기에서 받은 preview_token')


INQUIRY_CHILDREN = (
    s.corrections, s.answers, s.events, s.provider_inbox, s.provider_calls,
    s.outbox, s.delivery_leases, s.worker_receipts, s.results,
    s.review_holds, s.review_actions, s.fallback_tasks, s.calls, s.questions,
)
ACADEMY_CHILDREN = (
    s.academy_classes, s.academy_call_hours, s.academy_setting_states,
    s.academy_policies, s.academy_profiles,
)
DELETE_TABLES = tuple(t.name for t in (*INQUIRY_CHILDREN, s.inquiries, *ACADEMY_CHILDREN, s.academies))
BLOCK_MESSAGES = {
    'inquiries_exist': '이 학원에 문의가 남아 있습니다. 필요한 문의를 먼저 개별 삭제해 주세요.',
    'inquiry_in_progress': '처리 중인 문의는 삭제할 수 없습니다.',
    'call_in_progress': '통화 또는 결과 수신이 진행 중입니다.',
    'delivery_in_progress': '워커 전달 처리가 진행 중입니다. 완료 후 다시 확인해 주세요.',
    'recording_preservation_required': '녹음 참조가 있어 별도 보관 확인이 필요합니다. 이 API에서는 삭제하지 않습니다.',
}


class AdminManagement:
    def __init__(self, service):
        self.service = service

    def _admin(self, c, actor):
        # Check persisted role again within the mutation transaction, never a submitted role.
        account = c.execute(select(s.accounts.c.role, s.accounts.c.enabled)
            .where(s.accounts.c.user_id == actor).with_for_update()).first()
        if account is None or account.role != 'admin' or not account.enabled:
            raise HTTPException(403, 'Administrator role required')

    def _academy(self, c, acid):
        row = c.execute(select(s.academies).where(s.academies.c.id == acid)).mappings().first()
        if row is None:
            raise HTTPException(404, 'Academy not found')
        return dict(row)

    def _detail(self, c, acid):
        row = self._academy(c, acid)
        profile = c.execute(select(s.academy_profiles)
            .where(s.academy_profiles.c.academy_id == acid)).mappings().first()
        state = c.execute(select(s.academy_setting_states)
            .where(s.academy_setting_states.c.academy_id == acid)).mappings().first()
        return aware(dict(academy_id=acid, name=row['name'], phone=row['phone'], region=row['region'],
            is_mock=row['is_mock'], address=profile['address'] if profile else None,
            owner_id=profile['owner_id'] if profile else None, version=state['version'] if state else 0,
            updated_at=state['last_modified_at'] if state else None,
            inquiry_count=c.execute(select(func.count()).select_from(s.inquiries)
                .where(s.inquiries.c.academy_id == acid)).scalar_one(),
            **self.service.read_academy_settings(c, acid)))

    def list_academies(self, query, limit, offset):
        with self.service.engine.connect() as c:
            condition = or_(s.academies.c.name.contains(query, autoescape=True),
                s.academies.c.phone.contains(query, autoescape=True))
            total = c.execute(select(func.count()).select_from(s.academies).where(condition)).scalar_one()
            rows = c.execute(select(s.academies.c.id).where(condition)
                .order_by(s.academies.c.name, s.academies.c.id).limit(limit).offset(offset)).scalars()
            return dict(items=[self._detail(c, acid) for acid in rows], total=total, limit=limit, offset=offset)

    def academy(self, acid):
        with self.service.engine.connect() as c:
            return self._detail(c, acid)

    def _active(self, c, iids):
        return c.execute(select(s.calls.c.id).where(s.calls.c.inquiry_id.in_(iids),
            s.calls.c.status.not_in(['finished', 'timeout']))).first() is not None

    def edit_academy(self, acid, body, actor):
        fields = body.model_fields_set - {'version'}
        with self.service.engine.begin() as c:
            self.service.lock(c)
            self._admin(c, actor)
            row = self._academy(c, acid)
            state = c.execute(select(s.academy_setting_states)
                .where(s.academy_setting_states.c.academy_id == acid)).mappings().first()
            if body.version != (state['version'] if state else 0):
                raise HTTPException(409, '학원 정보가 변경되었습니다. 다시 조회해 주세요.')
            iids = select(s.inquiries.c.id).where(s.inquiries.c.academy_id == acid)
            if self._active(c, iids):
                raise HTTPException(409, '진행 중인 통화가 있어 수정할 수 없습니다.')
            if 'phone' in fields and body.phone is None and not row['is_mock']:
                raise HTTPException(422, '실제 학원의 전화번호는 비울 수 없습니다.')
            profile_fields = {key: getattr(body, key) for key in fields & {'name', 'phone', 'region'}}
            if profile_fields:
                c.execute(update(s.academies).where(s.academies.c.id == acid).values(**profile_fields))
            if 'address' in fields:
                profile = c.execute(select(s.academy_profiles.c.academy_id)
                    .where(s.academy_profiles.c.academy_id == acid)).first()
                if profile is None:
                    raise HTTPException(409, '소유자 등록이 없는 학원에는 주소를 저장할 수 없습니다.')
                c.execute(update(s.academy_profiles).where(s.academy_profiles.c.academy_id == acid)
                    .values(address=body.address))
            now = self.service.now()
            if 'classes' in fields:
                c.execute(s.academy_classes.delete().where(s.academy_classes.c.academy_id == acid))
                for item in body.classes:
                    c.execute(s.academy_classes.insert().values(id=uid(), academy_id=acid,
                        created_at=now, updated_at=now, **item.model_dump()))
            if 'call_hours' in fields:
                c.execute(s.academy_call_hours.delete().where(s.academy_call_hours.c.academy_id == acid))
                for item in body.call_hours:
                    c.execute(s.academy_call_hours.insert().values(academy_id=acid, created_at=now,
                        day_of_week=item.day_of_week, start_time=time.fromisoformat(item.start_time),
                        end_time=time.fromisoformat(item.end_time)))
            values = dict(last_modified_at=now, version=body.version + 1)
            for key, flag in [('classes', 'is_class_configured'), ('call_hours', 'is_call_hours_configured')]:
                if key in fields:
                    values[flag] = True
            if state:
                c.execute(update(s.academy_setting_states).where(s.academy_setting_states.c.academy_id == acid).values(**values))
            else:
                c.execute(s.academy_setting_states.insert().values(academy_id=acid,
                    **{'is_class_configured': False, 'is_call_hours_configured': False, **values}))
            result = self._detail(c, acid)
        self._audit('edit_academy', actor, acid, dict(fields=sorted(fields)))
        return result

    def list_inquiries(self, academy_id, inquirer_id, status, limit, offset):
        conditions = []
        for value, column in [(academy_id, s.inquiries.c.academy_id),
                              (inquirer_id, s.inquiries.c.inquirer_id), (status, s.inquiries.c.status)]:
            if value is not None:
                conditions.append(column == value)
        with self.service.engine.connect() as c:
            total = c.execute(select(func.count()).select_from(s.inquiries).where(*conditions)).scalar_one()
            rows = c.execute(select(s.inquiries.c.id.label('inquiry_id'), s.inquiries.c.academy_id,
                s.academies.c.name.label('academy_name'), s.inquiries.c.inquirer_id,
                s.accounts.c.login_name.label('inquirer_login'), s.inquiries.c.status,
                s.inquiries.c.created_at, s.inquiries.c.failure_reason)
                .join(s.academies, s.academies.c.id == s.inquiries.c.academy_id)
                .outerjoin(s.accounts, s.accounts.c.user_id == s.inquiries.c.inquirer_id)
                .where(*conditions).order_by(s.inquiries.c.created_at.desc(), s.inquiries.c.id)
                .limit(limit).offset(offset)).mappings().all()
            return aware(dict(items=[dict(r) for r in rows], total=total, limit=limit, offset=offset))

    def _snapshot(self, c, kind, target_id):
        if kind == 'academy':
            target = self._academy(c, target_id)
            scopes = [(t, t.c.academy_id == target_id) for t in ACADEMY_CHILDREN]
            inquiries = list(c.execute(select(s.inquiries.c.id).where(s.inquiries.c.academy_id == target_id)).scalars())
            blockers = ['inquiries_exist'] if inquiries else []
            target_table = s.academies
        else:
            row = c.execute(select(s.inquiries).where(s.inquiries.c.id == target_id)).mappings().first()
            if row is None:
                raise HTTPException(404, 'Inquiry not found')
            target = dict(row)
            call_ids = select(s.calls.c.id).where(s.calls.c.inquiry_id == target_id)
            scopes = [(t, t.c.inquiry_id == target_id if 'inquiry_id' in t.c else t.c.call_id.in_(call_ids))
                      for t in INQUIRY_CHILDREN]
            inquiries = [target_id]
            blockers = ['inquiry_in_progress'] if target['status'] == 'calling' else []
            if self._active(c, inquiries):
                blockers.append('call_in_progress')
            if c.execute(select(s.delivery_leases.c.call_id).where(s.delivery_leases.c.call_id.in_(call_ids),
                s.delivery_leases.c.lease_until > self.service.now())).first():
                blockers.append('delivery_in_progress')
            target_table = s.inquiries
        rows = {target_table.name: [target]}
        for table, condition in scopes:
            rows[table.name] = [dict(r) for r in c.execute(select(table).where(condition)).mappings()]
        if kind == 'inquiry' and any(r['payload'].get('recording_url')
                for name in [s.results.name, s.corrections.name] for r in rows[name]):
            blockers.append('recording_preservation_required')
        canonical = {name: sorted(json.dumps(r, sort_keys=True, default=str, ensure_ascii=False) for r in values)
                     for name, values in rows.items()}
        token = hashlib.sha256(json.dumps(dict(kind=kind, target_id=target_id, rows=canonical,
            inquiries=sorted(inquiries)), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        preview = dict(kind=kind, target_id=target_id, can_delete=not blockers,
            blockers=[dict(code=b, message=BLOCK_MESSAGES[b]) for b in blockers],
            counts={name: len(values) for name, values in rows.items()},
            linked_inquiries=len(inquiries) if kind == 'academy' else 1, preview_token=token,
            scope='공유 DB의 대상·연결 기록. 회원 계정 및 외부 녹음·워커 보관본은 삭제하지 않습니다.')
        return preview, scopes, target_table

    def preview_delete(self, kind, target_id):
        with self.service.engine.begin() as c:
            self.service.lock(c)
            return self._snapshot(c, kind, target_id)[0]

    def delete(self, kind, target_id, body, actor):
        if body.confirm_id != target_id:
            raise HTTPException(422, 'confirm_id가 삭제 대상과 일치하지 않습니다.')
        try:
            with self.service.engine.begin() as c:
                self.service.lock(c)
                self._admin(c, actor)
                preview, scopes, table = self._snapshot(c, kind, target_id)
                if preview['preview_token'] != body.preview_token:
                    raise HTTPException(409, '삭제 대상이 변경되었습니다. 미리보기를 다시 조회해 주세요.')
                if not preview['can_delete']:
                    raise HTTPException(409, dict(code='delete_blocked', blockers=preview['blockers']))
                for child, condition in scopes:
                    c.execute(child.delete().where(condition))
                c.execute(table.delete().where(table.c.id == target_id))
        except DBAPIError as error:
            if getattr(error.orig, 'args', (None,))[0] in (1142, 1143, 1227):
                raise HTTPException(503, '관리 기능용 DB 삭제 권한이 준비되지 않았습니다. 서버 적용 안내를 확인해 주세요.') from None
            raise
        result = dict(deleted=True, kind=kind, target_id=target_id, deleted_counts=preview['counts'])
        self._audit('delete_' + kind, actor, target_id, dict(counts=preview['counts']))
        return result

    @staticmethod
    def _audit(action, actor, target_id, metadata):
        # IDs and affected fields/counts only; no phone, student, password, or transcript values.
        logging.getLogger('uvicorn.error').info('admin_management %s', json.dumps(
            dict(action=action, actor_id=actor, target_id=target_id, **metadata), sort_keys=True))
