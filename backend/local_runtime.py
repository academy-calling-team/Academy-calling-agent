"""Portable MySQL factories. The historical function name preserves core imports."""
from sqlalchemy import create_engine
from settings import database_url

def local_engine():
    return create_engine(database_url(), pool_pre_ping=True)

def test_engine():
    return create_engine(database_url(test=True), pool_pre_ping=True)
