"""Explicit local mock runner. Never calls a telephone provider."""
import argparse
import json
import time
import redis
from redis.exceptions import RedisError
from local_runtime import local_engine
from service import Service
from redis_queue import RedisQueue
from worker import MockWorker,make_result
from contracts import ResultInput
from settings import redis_url, require_mock_mode

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--simulate-results',action='store_true',help='Store explicitly synthetic answers, not measured voice results')
    args=parser.parse_args()
    require_mock_mode()
    engine=local_engine(); service=Service(engine,allow_legacy_tokens=False)
    client=redis.Redis.from_url(redis_url(),decode_responses=True,
        socket_connect_timeout=2,socket_timeout=3)
    # Uses the existing mock contract with an in-process placeholder; no external credential needed.
    worker=MockWorker(engine,'local-mock-runner-placeholder')
    queue=RedisQueue(service,client)
    try:
        while True:
            try:
                report=queue.step(worker)
                if args.simulate_results:
                    from sqlalchemy import select
                    from schema import calls,results
                    with engine.connect() as c:
                        pending=list(c.execute(select(calls.c.id,calls.c.dispatch_payload)
                            .outerjoin(results).where(calls.c.status=='accepted',results.c.call_id.is_(None))).mappings())
                    for call in pending:
                        if call['dispatch_payload']['is_mock'] is not True: continue
                        service.result(call['id'],ResultInput.model_validate(make_result(call['dispatch_payload'])))
                    report['synthetic_results']=len(pending)
                print(json.dumps(report,ensure_ascii=False))
            except RedisError:
                # Reservations/outbox survive the outage; no direct worker fallback or redial.
                print(json.dumps(dict(queue='unavailable',action='keep_mysql_outbox'),ensure_ascii=False))
                if args.once: raise SystemExit(1) from None
            if args.once: break
            time.sleep(2)
    finally:
        worker.close();client.close();engine.dispose()
if __name__=='__main__':main()
