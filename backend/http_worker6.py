"""Worker contract adapter with uncertain-acceptance lookup. Real dialing stays disabled."""
from urllib.parse import urlparse
import httpx

class WorkerHttpAdapter:
    def __init__(self,url,internal_key,transport=None):
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
            r=self.client.get('/internal/calls/'+cid)
            reply=r.json() if r.status_code==200 else {}
        except (httpx.RequestError,ValueError):return None
        return reply if isinstance(reply,dict) and reply.get('call_id')==cid and reply.get('accepted') is True else None
    def accept(self,payload):
        if payload.get('is_mock') is not True:raise ValueError('Real dialing is disabled in this development adapter')
        try:
            r=self.client.post('/internal/calls',json=payload)
            reply=r.json() if r.status_code==202 else None
        except (httpx.RequestError,ValueError):reply=None
        if not isinstance(reply,dict) or reply.get('call_id')!=payload['call_id'] or reply.get('accepted') is not True:
            reply=self.lookup(payload['call_id'])
        if reply is None:raise ConnectionError('Worker acceptance unknown; keep same call ID')
        return reply
    def close(self):self.client.close()
