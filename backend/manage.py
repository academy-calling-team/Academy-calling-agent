"""Explicit initialization and synthetic academy seed for a dedicated development DB."""
import argparse
from sqlalchemy import select
from local_runtime import local_engine
from service import Service
from schema import academies
from settings import require_mock_mode

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init-db','seed-mock'])
    action = parser.parse_args().action
    require_mock_mode()
    engine = local_engine()
    try:
        if action == 'init-db':
            Service(engine, allow_legacy_tokens=False).initialize()
            print('Development schema initialized. Existing tables were not dropped.')
        else:
            with engine.begin() as c:
                if not c.execute(select(academies.c.id).where(academies.c.id=='demo-academy')).first():
                    c.execute(academies.insert().values(id='demo-academy', name='가상 시험 학원',
                        region='대구 북구 침산동', phone=None, is_mock=True,
                        hours=[dict(weekday=i,start_minute=0,end_minute=1440) for i in range(7)]))
            print('Synthetic academy prepared; no real phone number or provider request.')
    finally:
        engine.dispose()

if __name__ == '__main__':
    main()
