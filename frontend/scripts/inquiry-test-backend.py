"""Isolated SQLite API fixture for inquiry-smoke.mjs. Never connects to MySQL/Redis."""
import argparse
import sys
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--backend-dir', type=Path)
parser.add_argument('--port', type=int, default=18770)
args = parser.parse_args()
backend = args.backend_dir
if backend is None:
    matches = list(Path(__file__).resolve().parents[2].glob('Academy-calling-agent-backend*/backend'))
    if len(matches) != 1:
        parser.error('Specify --backend-dir with the team backend source directory.')
    backend = matches[0]
if not (backend / 'api.py').is_file():
    parser.error('Backend source directory is unavailable.')
sys.path.insert(0, str(backend.resolve()))
from sqlalchemy import create_engine
from api import create_app
from service import Service
from schema import academies
from worker import MockWorker
import uvicorn

with tempfile.TemporaryDirectory(prefix='hakwon-inquiry-test-') as folder:
    engine = create_engine('sqlite:///' + str(Path(folder) / 'check.sqlite'))
    service = Service(engine, allow_legacy_tokens=False)
    service.initialize()
    with engine.begin() as connection:
        connection.execute(academies.insert().values(
            id='demo-academy', name='격리 검증 학원', region='대구 북구 침산동',
            phone=None, is_mock=True,
            hours=[dict(weekday=i, start_minute=0, end_minute=1440) for i in range(7)]))
    worker = MockWorker(engine, 'synthetic-inquiry-check-only')
    try:
        app = create_app(engine, 'synthetic-inquiry-check-only', service, with_auth=True, worker=worker)
        print('Isolated SQLite test API only; accounts and inquiries are discarded on exit.', flush=True)
        uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
    finally:
        worker.close()
        engine.dispose()
