"""Development accounts and revocable opaque sessions. No external identity proof."""
import secrets
from datetime import timedelta
from pwdlib import PasswordHash
from fastapi import HTTPException
from sqlalchemy import select,update
from schema import users,accounts,sessions
from service import uid,digest,aware

PASSWORDS=PasswordHash.recommended()
DUMMY_HASH=PASSWORDS.hash(secrets.token_urlsafe(32))
class AuthStore:
    def __init__(self,service,session_seconds=3600):
        if not 1<=session_seconds<=86400:raise ValueError('Invalid session lifetime')
        self.service=service;self.session_seconds=session_seconds
    def register(self,body):
        hashed=PASSWORDS.hash(body.password.get_secret_value())
        with self.service.engine.begin() as c:
            self.service.lock(c)
            if c.execute(select(accounts.c.user_id).where(accounts.c.login_name==body.login_name)).first():
                raise HTTPException(409,'Login name already registered')
            user_id=uid()
            # An unreachable legacy digest satisfies the old schema without issuing an old token.
            c.execute(users.insert().values(id=user_id,token_hash=digest(secrets.token_urlsafe(32))))
            c.execute(accounts.insert().values(user_id=user_id,login_name=body.login_name,password_hash=hashed,
                role='member',enabled=True,failed_logins=0))
        return dict(inquirer_id=user_id,login_name=body.login_name,role='member')
    def login(self,body):
        with self.service.engine.connect() as c:
            snapshot=c.execute(select(accounts).where(accounts.c.login_name==body.login_name)).mappings().first()
        ok=PASSWORDS.verify(body.password.get_secret_value(),snapshot['password_hash'] if snapshot else DUMMY_HASH)
        if snapshot is None:raise HTTPException(401,'Invalid login')
        failure=None;reply=None
        with self.service.engine.begin() as c:
            self.service.lock(c)
            account=c.execute(select(accounts).where(accounts.c.user_id==snapshot['user_id'])).mappings().one()
            if not account['enabled']:failure=HTTPException(401,'Invalid login')
            elif account['locked_until'] and account['locked_until']>self.service.now():
                failure=HTTPException(429,'Login temporarily locked')
            elif not ok or account['password_hash']!=snapshot['password_hash']:
                count=account['failed_logins']+1 if not account['locked_until'] else 1
                c.execute(update(accounts).where(accounts.c.user_id==account['user_id']).values(failed_logins=count,
                    locked_until=self.service.now()+timedelta(seconds=300) if count>=5 else None))
                failure=HTTPException(401,'Invalid login')
            else:
                token=secrets.token_urlsafe(32);expires=self.service.now()+timedelta(seconds=self.session_seconds)
                c.execute(update(accounts).where(accounts.c.user_id==account['user_id']).values(failed_logins=0,locked_until=None))
                c.execute(sessions.insert().values(token_hash=digest(token),id=uid(),user_id=account['user_id'],
                    created_at=self.service.now(),expires_at=expires,revoked=False))
                reply=aware(dict(access_token=token,token_type='bearer',expires_at=expires,inquirer_id=account['user_id']))
        # Failed attempts must commit, so do not raise inside the transaction.
        if failure:raise failure
        return reply
    def identity(self,token):
        with self.service.engine.connect() as c:
            user_id=self.service.owner(c,token)
            row=c.execute(select(accounts.c.login_name,accounts.c.role,sessions.c.expires_at)
                .join(sessions,accounts.c.user_id==sessions.c.user_id)
                .where(accounts.c.user_id==user_id,sessions.c.token_hash==digest(token))).mappings().first()
            if not row:raise HTTPException(401,'Session required')
            return aware(dict(inquirer_id=user_id,**row))
    def logout(self,token):
        with self.service.engine.begin() as c:
            self.service.owner(c,token)
            c.execute(update(sessions).where(sessions.c.token_hash==digest(token)).values(revoked=True))
        return dict(logged_out=True)
    def admin(self,token):
        identity=self.identity(token)
        if identity['role']!='admin':raise HTTPException(403,'Administrator role required')
        return identity['inquirer_id']
