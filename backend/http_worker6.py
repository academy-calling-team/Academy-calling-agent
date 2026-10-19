"""Voice HTTP adapter. Real dispatch requires persisted test authorization."""
from urllib.parse import urlparse, quote
import httpx
from worker_errors import WorkerRejected, WorkerProtocolError

class WorkerHttpAdapter:
    def __init__(self,url,internal_key,transport=None,authorize_real=None):
        self.authorize_real=authorize_real
        parsed=urlparse(url)
        local=parsed.hostname in {'127.0.0.1','localhost'}
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Worker URL must not embed access data or query parameters')
        if not local and parsed.scheme!='https':raise ValueError('External worker requires HTTPS')
        if parsed.scheme not in {'http','https'} or not parsed.hostname:raise ValueError('Invalid worker URL')
        if not internal_key:raise ValueError('Worker access must be configured at runtime')
        self.client=httpx.Client(base_url=url.rstrip('/'),transport=transport,timeout=5,
            trust_env=False,follow_redirects=False,headers={'X-Internal-Key':internal_key})
    def lookup(self,cid):
        try:
            r=self.client.get('/internal/calls/'+quote(cid,safe=''))
            reply=r.json() if r.status_code==200 else {}
        except (httpx.RequestError,ValueError):return None
        return reply if isinstance(reply,dict) and reply.get('call_id')==cid and reply.get('accepted') is True else None
    def accept(self,payload):
        if payload.get('is_mock') is not True:
            if self.authorize_real is None:
                raise ValueError('Real dialing is disabled without explicit test authorization')
            if not self.authorize_real(payload):raise WorkerRejected(403)
        try:
            r=self.client.post('/internal/calls',json=payload)
        except httpx.RequestError:
            reply=self.lookup(payload['call_id'])
            if reply is None:raise ConnectionError('Worker acceptance unknown; keep same call ID') from None
            return reply
        if r.status_code==429 or 500<=r.status_code<600:
            raise ConnectionError(f'Worker temporarily unavailable: HTTP {r.status_code}')
        if 400<=r.status_code<500:
            raise WorkerRejected(r.status_code)
        if r.status_code!=202:
            raise WorkerProtocolError(f'Unexpected worker status: HTTP {r.status_code}')
        try:reply=r.json()
        except ValueError:raise WorkerProtocolError('Invalid worker acceptance JSON') from None
        if not isinstance(reply,dict) or reply.get('call_id')!=payload['call_id'] or reply.get('accepted') is not True:
            raise WorkerProtocolError('Worker acceptance receipt does not match request')
        return reply
    def close(self):self.client.close()
