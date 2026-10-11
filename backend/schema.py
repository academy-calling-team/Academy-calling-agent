"""Additive development schema. Table prefix isolates the old prototype."""
from sqlalchemy import (MetaData, Table, Column, String, Integer, Boolean, DateTime,
                        Text, JSON, ForeignKey, UniqueConstraint, CheckConstraint)

metadata = MetaData()
opts = dict(mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_bin')
def table(name, *cols):
    return Table('w5_' + name, metadata, *cols, **opts)
users = table('inquirers', Column('id', String(36), primary_key=True),
              Column('token_hash', String(64), nullable=False, unique=True))
academies = table('academies', Column('id', String(36), primary_key=True),
    Column('name', String(100), nullable=False), Column('region', String(80), nullable=False),
    Column('phone', String(30)), Column('is_mock', Boolean, nullable=False),
    Column('hours', JSON, nullable=False))
inquiries = table('inquiries', Column('id', String(36), primary_key=True),
    Column('inquirer_id', String(36), ForeignKey(users.c.id), nullable=False, index=True),
    Column('academy_id', String(36), ForeignKey(academies.c.id), nullable=False),
    Column('request_key', String(80), nullable=False), Column('payload_hash', String(64), nullable=False),
    Column('student', JSON, nullable=False), Column('status', String(20), nullable=False),
    Column('priority', Integer, nullable=False, default=0),
    Column('created_at', DateTime, nullable=False), Column('next_at', DateTime, nullable=False),
    Column('failure_reason', String(80)), Column('fallback_required', Boolean, nullable=False, default=False),
    UniqueConstraint('inquirer_id', 'request_key', name='w5_uq_request'),
    CheckConstraint("status IN ('queued','calling','retry_wait','completed','failed')", name='w5_ck_status'))
questions = table('questions', Column('id', String(36), primary_key=True),
    Column('inquiry_id', String(36), ForeignKey(inquiries.c.id), nullable=False, index=True),
    Column('code', String(30), nullable=False), Column('position', Integer, nullable=False),
    UniqueConstraint('inquiry_id', 'code', name='w5_uq_question_code'),
    UniqueConstraint('inquiry_id', 'position', name='w5_uq_question_position'))
calls = table('calls', Column('id', String(36), primary_key=True),
    Column('inquiry_id', String(36), ForeignKey(inquiries.c.id), nullable=False, index=True),
    Column('attempt_no', Integer, nullable=False), Column('status', String(30), nullable=False),
    Column('outcome', String(30)), Column('created_at', DateTime, nullable=False),
    Column('last_event_at', DateTime), Column('deadline', DateTime, nullable=False),
    Column('dispatch_payload', JSON, nullable=False), Column('delivery_count', Integer, nullable=False, default=0),
    UniqueConstraint('inquiry_id', 'attempt_no', name='w5_uq_attempt'),
    CheckConstraint('attempt_no > 0', name='w5_ck_attempt'))
events = table('events', Column('id', String(80), primary_key=True),
    Column('call_id', String(36), ForeignKey(calls.c.id), nullable=False, index=True),
    Column('type', String(30), nullable=False), Column('occurred_at', DateTime, nullable=False),
    Column('received_at', DateTime, nullable=False), Column('payload_hash', String(64), nullable=False),
    Column('applied', Boolean, nullable=False))
results = table('results', Column('call_id', String(36), ForeignKey(calls.c.id), primary_key=True),
    Column('result_id', String(80), unique=True, nullable=False),
    Column('payload_hash', String(64), nullable=False), Column('payload', JSON, nullable=False),
    Column('received_at', DateTime, nullable=False), Column('applied', Boolean, nullable=False))
answers = table('answers', Column('call_id', String(36), ForeignKey(calls.c.id), primary_key=True),
    Column('question_id', String(36), ForeignKey(questions.c.id), primary_key=True),
    Column('asked', Boolean, nullable=False), Column('answered', Boolean, nullable=False),
    Column('yes_no', Boolean), Column('reason', String(30)), Column('detail', Text, nullable=False))
control = table('control', Column('id', String(36), primary_key=True))
worker_receipts = table('mock_worker_receipts', Column('call_id', String(36), primary_key=True),
    Column('payload_hash', String(64), nullable=False), Column('payload', JSON, nullable=False),
    Column('received_at', DateTime, nullable=False))
outbox = table('dispatch_outbox',
    Column('id', String(36), primary_key=True),
    Column('call_id', String(36), ForeignKey(calls.c.id), unique=True, nullable=False),
    Column('created_at', DateTime, nullable=False), Column('last_published_at', DateTime))
delivery_leases = table('delivery_leases',
    Column('call_id', String(36), ForeignKey(calls.c.id), primary_key=True),
    Column('claim_id', String(36), nullable=False), Column('lease_until', DateTime, nullable=False))
corrections = table('result_corrections',
    Column('id', String(36), primary_key=True),
    Column('call_id', String(36), ForeignKey(results.c.call_id), nullable=False, index=True),
    Column('revision', Integer, nullable=False), Column('reviewer', String(100), nullable=False),
    Column('reason', String(1000), nullable=False), Column('payload', JSON, nullable=False),
    Column('created_at', DateTime, nullable=False),
    UniqueConstraint('call_id', 'revision', name='w5_uq_correction_revision'))
academy_policies = table('academy_policies',
    Column('academy_id', String(36), ForeignKey(academies.c.id), primary_key=True),
    Column('enabled', Boolean, nullable=False, default=True),
    Column('max_concurrent', Integer, nullable=False, default=1),
    Column('cooldown_seconds', Integer, nullable=False, default=300),
    Column('closed_dates', JSON, nullable=False, default=list))

# Week 6 adds tables only; the week 5 schema and archived artifacts remain intact.
def week6(name,*cols): return Table('w6_'+name,metadata,*cols,**opts)
accounts=week6('accounts',
    Column('user_id',String(36),ForeignKey(users.c.id),primary_key=True),
    Column('login_name',String(32),nullable=False,unique=True),
    Column('password_hash',String(500),nullable=False),Column('role',String(16),nullable=False,default='member'),
    Column('enabled',Boolean,nullable=False,default=True),
    Column('failed_logins',Integer,nullable=False,default=0),Column('locked_until',DateTime))
sessions=week6('sessions',Column('token_hash',String(64),primary_key=True),
    Column('id',String(36),unique=True,nullable=False),
    Column('user_id',String(36),ForeignKey(accounts.c.user_id),nullable=False,index=True),
    Column('created_at',DateTime,nullable=False),Column('expires_at',DateTime,nullable=False),
    Column('revoked',Boolean,nullable=False,default=False))
review_holds=week6('review_holds',Column('inquiry_id',String(36),ForeignKey(inquiries.c.id),primary_key=True),
    Column('call_id',String(36),ForeignKey(calls.c.id),nullable=False),
    Column('reason',String(80),nullable=False),Column('open',Boolean,nullable=False),
    Column('created_at',DateTime,nullable=False))
review_actions=week6('review_actions',Column('id',String(36),primary_key=True),
    Column('inquiry_id',String(36),ForeignKey(inquiries.c.id),nullable=False,index=True),
    Column('actor',String(100),nullable=False),Column('action',String(30),nullable=False),
    Column('reason',String(1000),nullable=False),Column('payload',JSON,nullable=False),
    Column('created_at',DateTime,nullable=False))
fallback_tasks=week6('fallback_tasks',Column('inquiry_id',String(36),ForeignKey(inquiries.c.id),primary_key=True),
    Column('status',String(30),nullable=False),Column('failure_reason',String(80),nullable=False),
    Column('message',Text),Column('created_at',DateTime,nullable=False),Column('reviewed_at',DateTime),
    Column('reviewer',String(100)),Column('review_reason',String(1000)),
    Column('dry_run_receipt',JSON))
provider_calls=week6('provider_calls',Column('call_id',String(36),ForeignKey(calls.c.id),primary_key=True),
    Column('provider',String(24),nullable=False),Column('external_id',String(100),nullable=False),
    Column('created_at',DateTime,nullable=False),
    UniqueConstraint('provider','external_id',name='w6_uq_provider_call'))
provider_inbox=week6('provider_inbox',Column('id',String(64),primary_key=True),
    Column('call_id',String(36),ForeignKey(calls.c.id),nullable=False,index=True),
    Column('type',String(60),nullable=False),Column('payload_hash',String(64),nullable=False),
    Column('status',String(30),nullable=False),Column('normalized',JSON,nullable=False),
    Column('error',String(100)),Column('received_at',DateTime,nullable=False),Column('processed_at',DateTime))
