import secrets
from fastapi import FastAPI, Header, Query, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from contracts import InquiryInput, EventInput, ResultInput, QUESTION_LABELS, REGIONS
from schema import academies
from service import Service

def create_app(engine,internal_key,service=None,worker=None,origins=None,with_auth=False,queue_client=None):
    if not internal_key: raise ValueError('Internal key must be configured')
    service=service or Service(engine)
    app=FastAPI(title='8조 백엔드 개발 API',version='0.4.0',
        description='노션 초안 기반 검토용 구현. 로컬 MySQL·Redis 목업 검증; 실통화·팀 연동·AWS 배포는 별도 확인.')
    app.state.service=service
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,error):
        # Default validation can echo submitted passwords/values. Return only field locations and reasons.
        return JSONResponse(status_code=422,content={'detail':[
            dict(loc=list(e['loc']),msg=e['msg'],type=e['type']) for e in error.errors()]})
    origins=origins or ['http://localhost:5173','http://127.0.0.1:5173']
    if '*' in origins: raise ValueError('Explicit CORS origins required')
    app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=['GET','POST'],
        allow_headers=['Authorization','Content-Type','Idempotency-Key'])
    bearer=HTTPBearer(auto_error=False)
    def auth(credentials:HTTPAuthorizationCredentials|None=Depends(bearer)):
        if credentials is None: raise HTTPException(401,'Bearer token required')
        return credentials.credentials
    def internal(x_internal_key:str|None=Header(None)):
        if not x_internal_key or not secrets.compare_digest(x_internal_key,internal_key):
            raise HTTPException(401,'Invalid internal key')
    @app.get('/health')
    def health():
        try:
            with engine.connect() as c: c.execute(text('SELECT 1'))
        except Exception: raise HTTPException(503,'Database unavailable') from None
        return dict(status='ok',database='ok',mode='development_mock')
    @app.get('/version')
    def version():
        import os
        return dict(commit=os.environ.get('DEPLOY_COMMIT_SHA', 'untracked'))
    @app.get('/api/options')
    def options():
        return dict(question_codes=QUESTION_LABELS,regions=REGIONS,
            grade=[f'E{i}' for i in range(1,7)]+[f'M{i}' for i in range(1,4)]+[f'H{i}' for i in range(1,4)],
            subject=['KOR','ENG','MATH','SCI','SOC'],level=['HIGH','MID','LOW'])
    @app.get('/api/academies')
    def list_academies():
        with engine.connect() as c:
            return [dict(academy_id=r['id'],name=r['name'],region=r['region'],is_mock=r['is_mock'])
                    for r in c.execute(select(academies)).mappings()]
    @app.post('/api/inquiries',status_code=201)
    def create(body:InquiryInput,token:str=Depends(auth),
               idempotency_key:str=Header(min_length=1,max_length=80)):
        return service.create(body,token,idempotency_key)
    @app.get('/api/inquiries')
    def list_owned(inquirer_id:str|None=None,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),
                   token:str=Depends(auth)):
        return service.list_owned(token,inquirer_id,limit,offset)
    @app.get('/api/inquiries/{inquiry_id}')
    def get(inquiry_id:str,token:str=Depends(auth)):
        return service.get(inquiry_id,token)
    @app.post('/internal/calls/{call_id}/events',dependencies=[Depends(internal)])
    def event(call_id:str,body:EventInput): return service.event(call_id,body)
    @app.post('/internal/calls/{call_id}/result',dependencies=[Depends(internal)])
    def result(call_id:str,body:ResultInput): return service.result(call_id,body)
    if worker is not None:
        @app.post('/internal/mock/tick',dependencies=[Depends(internal)])
        def tick(): return service.tick(worker)
    if with_auth:
        from auth6 import AuthStore
        from contracts6 import Credentials,RegistrationCredentials,CallbackReview,FallbackReview
        from contracts import CorrectionInput
        from ops6 import Operations
        service.allow_legacy_tokens=False
        auth_store=AuthStore(service);app.state.auth_store=auth_store
        ops=Operations(service,queue_client)
        def administrator(token:str=Depends(auth)):return auth_store.admin(token)
        @app.post('/auth/register',status_code=201)
        def register(body: RegistrationCredentials):
            return auth_store.register(body)
        @app.post('/auth/login')
        def login(body:Credentials):return auth_store.login(body)
        @app.post('/auth/logout')
        def logout(token:str=Depends(auth)):return auth_store.logout(token)
        @app.get('/auth/me')
        def me(token:str=Depends(auth)):return auth_store.identity(token)
        @app.get('/ready')
        def ready():
            state=ops.readiness()
            return JSONResponse(status_code=200 if state['ready'] else 503,content=state)
        @app.get('/ops/overview',dependencies=[Depends(administrator)])
        def overview():return ops.overview()
        @app.get('/ops/reviews',dependencies=[Depends(administrator)])
        def reviews(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0)):
            return ops.reviews(limit,offset)
        @app.post('/ops/inquiries/{inquiry_id}/callback')
        def callback_review(inquiry_id:str,body:CallbackReview,actor:str=Depends(administrator)):
            return service.review_callback(inquiry_id,body,actor)
        @app.post('/ops/inquiries/{inquiry_id}/fallback')
        def fallback_review(inquiry_id:str,body:FallbackReview,actor:str=Depends(administrator)):
            return service.review_fallback(inquiry_id,body,actor)
        @app.post('/ops/inquiries/{inquiry_id}/fallback/dry-run',dependencies=[Depends(administrator)])
        def fallback_dry_run(inquiry_id:str):return service.dry_run_fallback(inquiry_id)
        @app.post('/ops/calls/{call_id}/corrections')
        def correction(call_id:str,body:CorrectionInput,actor:str=Depends(administrator)):
            # The review author is authenticated; a submitted label cannot impersonate another actor.
            return service.correct_result(call_id,body.model_copy(update={'reviewer':actor}))
    return app
