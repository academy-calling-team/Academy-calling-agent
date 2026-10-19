"""Repository-local development configuration; never read the author's PC settings."""
import os
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=False)

def required(name):
    value = os.environ.get(name, '').strip()
    if not value:
        raise ValueError(f'{name} must be set in the repository .env or environment')
    return value

def database_url(test=False):
    prefix = 'TEST_' if test else ''
    host = required(prefix + 'MYSQL_HOST')
    database = required(prefix + 'MYSQL_DATABASE')
    if test and (host not in {'localhost','127.0.0.1'} or not database.endswith('_test')):
        raise ValueError('Integration tests require a local MySQL database ending in _test')
    try:
        port = int(required(prefix + 'MYSQL_PORT'))
    except ValueError:
        raise ValueError('MySQL port must be an integer') from None
    return URL.create('mysql+pymysql', username=required(prefix + 'MYSQL_USER'),
                      password=required(prefix + 'MYSQL_PASSWORD'), host=host,
                      port=port, database=database, query={'charset':'utf8mb4'})

def redis_url(test=False):
    value = required('TEST_REDIS_URL' if test else 'REDIS_URL')
    parsed = urlparse(value)
    if parsed.scheme not in {'redis','rediss'} or not parsed.hostname:
        raise ValueError('Redis URL must use redis:// or rediss://')
    if test and (parsed.hostname not in {'localhost','127.0.0.1'} or parsed.path in {'','/','/0'}):
        raise ValueError('Integration tests require local Redis and a nonzero database index')
    return value

def internal_key():
    value = required('INTERNAL_API_KEY')
    if len(value) < 32:
        raise ValueError('INTERNAL_API_KEY must contain at least 32 characters')
    return value

def cors_origins():
    values = [v.strip() for v in required('CORS_ORIGINS').split(',') if v.strip()]
    if not values or any(v == '*' or urlparse(v).scheme not in {'http','https'}
                         or not urlparse(v).hostname or urlparse(v).path not in {'','/'}
                         or urlparse(v).query or urlparse(v).fragment
                         or urlparse(v).username or urlparse(v).password for v in values):
        raise ValueError('CORS_ORIGINS must list explicit HTTP(S) origins')
    return [v.rstrip('/') for v in values]

def require_mock_mode():
    if required('APP_MODE') != 'development_mock':
        raise ValueError('Use development_mock; real test calls require explicit server authorization')
