"""Trusted local CLI for granting an admin role; no HTTP privilege escalation route."""
import argparse
import getpass
from pydantic import SecretStr
from sqlalchemy import select,update
from local_runtime import local_engine
from service import Service
from auth6 import AuthStore
from contracts6 import Credentials
from schema import accounts
from settings import require_mock_mode
from settings import require_mock_mode

def main():
    require_mock_mode()
    require_mock_mode()
    parser=argparse.ArgumentParser();parser.add_argument('login_name');args=parser.parse_args()
    password=SecretStr(getpass.getpass('New local administrator password (not shown): '))
    repeated=getpass.getpass('Repeat password: ')
    if password.get_secret_value()!=repeated:raise SystemExit('Passwords do not match')
    engine=local_engine();service=Service(engine,allow_legacy_tokens=False);service.initialize()
    try:
        store=AuthStore(service)
        user=store.register(Credentials(login_name=args.login_name,password=password))
        with engine.begin() as c:
            service.lock(c)
            c.execute(update(accounts).where(accounts.c.user_id==user['inquirer_id']).values(role='admin'))
        print('Local administrator created. Login through /auth/login; no access value printed.')
    finally:engine.dispose()
if __name__=='__main__':main()
