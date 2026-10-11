"""Development API factory; schema initialization is an explicit separate command."""
import redis
import uvicorn
from api import create_app
from local_runtime import local_engine
from service import Service
from settings import internal_key, redis_url, cors_origins, require_mock_mode

def build():
    require_mock_mode()
    key = internal_key()
    origins = cors_origins()
    queue_url = redis_url()
    engine = local_engine()
    service = Service(engine, allow_legacy_tokens=False)
    client = redis.Redis.from_url(queue_url, socket_connect_timeout=2, socket_timeout=3)
    app = create_app(engine, key, service, with_auth=True, queue_client=client, origins=origins)
    @app.on_event('shutdown')
    def close_resources():
        client.close()
        engine.dispose()
    return app

if __name__ == '__main__':
    uvicorn.run(build(), host='127.0.0.1', port=18770)
