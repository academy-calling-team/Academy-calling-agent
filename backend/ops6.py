"""Backend operations data, not a frontend dashboard."""
from fastapi import HTTPException
from sqlalchemy import select, func, text
from schema import (
    academies,
    inquiries,
    calls,
    results,
    corrections,
    review_holds,
    fallback_tasks,
    provider_inbox,
)
from service import aware


def _rate(numerator, denominator):
    return round(numerator / denominator, 3) if denominator else 0.0


class Operations:
    def __init__(self, service, queue_client=None):
        self.service, self.queue_client = service, queue_client

    def readiness(self):
        database = queue = False
        try:
            with self.service.engine.connect() as c:
                c.execute(text('SELECT 1'))
            database = True
        except Exception:
            pass
        if self.queue_client is not None:
            try:
                queue = self.queue_client.ping() is True
            except Exception:
                pass
        return dict(
            ready=database and queue,
            database='ok' if database else 'unavailable',
            queue='ok' if queue else 'unavailable',
            mode='development',
        )

    def overview(self):
        with self.service.engine.connect() as c:
            grouped = lambda table: dict(
                c.execute(select(table.c.status, func.count()).group_by(table.c.status)).all()
            )
            active = c.execute(
                select(func.count()).select_from(calls).where(calls.c.status.not_in(['finished', 'timeout']))
            ).scalar_one()
            holds = c.execute(
                select(func.count()).select_from(review_holds).where(review_holds.c.open == True)
            ).scalar_one()
            oldest = c.execute(
                select(func.min(inquiries.c.created_at)).where(inquiries.c.status == 'queued')
            ).scalar_one()
            return aware(
                dict(
                    scope='local_development_database',
                    inquiries=grouped(inquiries),
                    active_calls=active,
                    concurrency_limit=self.service.policy.max_concurrent,
                    open_reviews=holds,
                    fallback=grouped(fallback_tasks),
                    provider_inbox=grouped(provider_inbox),
                    oldest_queued_at=oldest,
                )
            )

    def reviews(self, limit=50, offset=0):
        with self.service.engine.connect() as c:
            rows = c.execute(
                select(review_holds)
                .where(review_holds.c.open == True)
                .order_by(review_holds.c.created_at, review_holds.c.inquiry_id)
                .limit(limit)
                .offset(offset)
            ).mappings()
            fallback = c.execute(
                select(
                    fallback_tasks.c.inquiry_id,
                    fallback_tasks.c.status,
                    fallback_tasks.c.failure_reason,
                    fallback_tasks.c.created_at,
                )
                .where(fallback_tasks.c.status == 'needs_review')
                .order_by(fallback_tasks.c.created_at, fallback_tasks.c.inquiry_id)
                .limit(limit)
                .offset(offset)
            ).mappings()
            return aware(dict(callbacks=[dict(r) for r in rows], fallback=[dict(r) for r in fallback]))

    def metrics(self, mode='all', academy_id=None):
        if mode not in ('all', 'real', 'mock'):
            raise ValueError('Invalid mode')
        with self.service.engine.connect() as c:
            if academy_id is not None:
                exists = c.execute(select(academies.c.id).where(academies.c.id == academy_id)).first()
                if exists is None:
                    raise HTTPException(404, 'Academy not found')

            filters = []
            if mode == 'real':
                filters.append(academies.c.is_mock.is_(False))
            elif mode == 'mock':
                filters.append(academies.c.is_mock.is_(True))
            if academy_id is not None:
                filters.append(inquiries.c.academy_id == academy_id)

            # 1. 문의 현황
            inq_rows = c.execute(
                select(inquiries.c.status, func.count())
                .select_from(inquiries.join(academies, academies.c.id == inquiries.c.academy_id))
                .where(*filters)
                .group_by(inquiries.c.status)
            ).all()
            inq_counts = dict(inq_rows)
            inq_total = sum(inq_counts.values())
            inq_completed = inq_counts.get('completed', 0)
            inq_failed = inq_counts.get('failed', 0)
            inq_in_progress = sum(
                inq_counts.get(st, 0) for st in ('queued', 'calling', 'retry_wait')
            )

            # 2. 발신 연결률 및 미연결 사유 분포
            call_rows = c.execute(
                select(calls.c.id, calls.c.status, calls.c.outcome)
                .select_from(
                    calls.join(inquiries, inquiries.c.id == calls.c.inquiry_id).join(
                        academies, academies.c.id == inquiries.c.academy_id
                    )
                )
                .where(calls.c.status.in_(['finished', 'timeout']), *filters)
            ).mappings().all()

            total_attempts = len(call_rows)
            connected_call_ids = []
            by_outcome = {}
            for row in call_rows:
                key = row['outcome'] if row['outcome'] is not None else 'timeout'
                by_outcome[key] = by_outcome.get(key, 0) + 1
                if row['outcome'] == 'answered':
                    connected_call_ids.append(row['id'])

            connected_count = len(connected_call_ids)

            # 3. 연결 통화의 유효 결과 및 최신 운영자 교정본(w5_result_corrections) 병합
            effective_payloads = []
            if connected_call_ids:
                res_rows = c.execute(
                    select(results.c.call_id, results.c.payload).where(
                        results.c.call_id.in_(connected_call_ids),
                        results.c.applied.is_(True),
                    )
                ).mappings().all()

                corr_rows = c.execute(
                    select(corrections.c.call_id, corrections.c.revision, corrections.c.payload)
                    .where(corrections.c.call_id.in_(connected_call_ids))
                    .order_by(corrections.c.call_id, corrections.c.revision.desc())
                ).mappings().all()

                latest_corr = {}
                for row in corr_rows:
                    if row['call_id'] not in latest_corr:
                        latest_corr[row['call_id']] = row['payload']

                for row in res_rows:
                    effective_payloads.append(latest_corr.get(row['call_id'], row['payload']))

            # 4. 질문 응답 확보율, 조건부 비중, 상담 수락률, 통화 시간·지연 집계
            q_total = 0
            q_answered = 0
            q_yes_total = 0
            q_yes_conditional = 0
            by_status = {
                'yes_unconditional': 0,
                'yes_conditional': 0,
                'no': 0,
                'direct_check': 0,
                'unconfirmed': 0,
                'not_asked': 0,
            }
            by_question_code = {}

            consult_accepted = 0
            consult_conditional = 0
            durations = []
            latencies = []

            for payload in effective_payloads:
                if payload.get('consult_accepted') is True:
                    consult_accepted += 1
                    consult_obj = payload.get('consult')
                    if isinstance(consult_obj, dict) and consult_obj.get('condition'):
                        consult_conditional += 1

                dur = payload.get('duration_sec')
                if isinstance(dur, (int, float)) and not isinstance(dur, bool):
                    durations.append(float(dur))

                lat = payload.get('latency')
                if isinstance(lat, (int, float)) and not isinstance(lat, bool):
                    latencies.append(float(lat))
                elif isinstance(lat, dict):
                    numeric_vals = [
                        float(v) for v in lat.values() if isinstance(v, (int, float)) and not isinstance(v, bool)
                    ]
                    if numeric_vals:
                        latencies.append(sum(numeric_vals) / len(numeric_vals))

                for ans in payload.get('answers') or []:
                    code = ans.get('question_code', 'unknown')
                    code_stat = by_question_code.setdefault(
                        code, {'total': 0, 'answered': 0, 'conditional': 0}
                    )
                    q_total += 1
                    code_stat['total'] += 1

                    if ans.get('answered') is True:
                        q_answered += 1
                        code_stat['answered'] += 1
                        if ans.get('yes_no') is True:
                            q_yes_total += 1
                            if ans.get('condition'):
                                q_yes_conditional += 1
                                code_stat['conditional'] += 1
                                by_status['yes_conditional'] += 1
                            else:
                                by_status['yes_unconditional'] += 1
                        else:
                            by_status['no'] += 1
                    else:
                        if ans.get('asked') is False or ans.get('reason') == 'not_asked':
                            by_status['not_asked'] += 1
                        elif ans.get('reason') == 'redirect':
                            by_status['direct_check'] += 1
                        else:
                            by_status['unconfirmed'] += 1

            for code_stat in by_question_code.values():
                code_stat['answer_rate'] = _rate(code_stat['answered'], code_stat['total'])

            evaluated_calls = len(effective_payloads)
            return {
                'scope': {
                    'mode': mode,
                    'academy_id': academy_id,
                },
                'inquiries': {
                    'total': inq_total,
                    'completed': inq_completed,
                    'failed': inq_failed,
                    'in_progress': inq_in_progress,
                    'completion_rate': _rate(inq_completed, inq_total),
                },
                'calls': {
                    'total_attempts': total_attempts,
                    'connected': connected_count,
                    'connection_rate': _rate(connected_count, total_attempts),
                    'by_outcome': by_outcome,
                },
                'questions': {
                    'total_questions': q_total,
                    'answered_count': q_answered,
                    'answer_rate': _rate(q_answered, q_total),
                    'conditional_ratio_in_yes': _rate(q_yes_conditional, q_yes_total),
                    'by_status': by_status,
                    'by_question_code': by_question_code,
                },
                'consult': {
                    'evaluated_calls': evaluated_calls,
                    'accepted': consult_accepted,
                    'acceptance_rate': _rate(consult_accepted, evaluated_calls),
                    'conditional_accepted': consult_conditional,
                },
                'timing': {
                    'avg_duration_sec': round(sum(durations) / len(durations), 2) if durations else None,
                    'avg_latency_ms': round(sum(latencies) / len(latencies), 2) if latencies else None,
                },
            }