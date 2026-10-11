"""HTTP acceptance adapter for local contract verification only."""
from urllib.parse import urlparse
import httpx

class LocalHttpWorker:
    def __init__(self,url,internal_key):
        parsed=urlparse(url)
        if parsed.scheme!='http' or parsed.hostname not in ['127.0.0.1','localhost']:
            raise ValueError('This verification adapter permits only local mock worker URLs')
        self.client=httpx.Client(base_url=url.rstrip('/'),timeout=5,trust_env=False,
            headers={'X-Internal-Key':internal_key})
    def accept(self,payload):
        if payload.get('is_mock') is not True: raise ValueError('Mock requests only')
        try: response=self.client.post('/internal/calls',json=payload)
        except httpx.TimeoutException: raise TimeoutError('Worker acceptance unknown') from None
        except httpx.RequestError: raise ConnectionError('Worker unreachable') from None
        if response.status_code!=202: raise ConnectionError('Worker did not acknowledge acceptance')
        try: return response.json()
        except ValueError: raise ConnectionError('Invalid worker acknowledgment') from None
    def close(self):self.client.close()
