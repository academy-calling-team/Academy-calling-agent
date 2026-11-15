"""Offline regression for the ClawOps agent tool after removing the comparison tool."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clawops_agents as tools
import setup_service_agent as service


def test_service_body_preserves_model_voice_and_dynamic_prompt():
    body = service.body()
    assert body['name'] == service.NAME
    assert body['instructions'] == service.PROMPT.read_text(encoding='utf-8').strip()
    assert body['greeting'] is False
    assert body['configuration'] == {
        'outputMode': 'live', 'language': 'ko',
        'knowledge': {'enabled': False, 'topK': 3},
        'llm': {'provider': 'openai-live', 'model': 'gpt-live-1', 'voice': 'marin',
                'backend_model': 'gpt-5.6-luna', 'backend_reasoning_effort': 'none'},
    }


def test_service_create_uses_only_clawops_settings(monkeypatch):
    env = {'CLAWOPS_ACCOUNT_ID': 'synthetic-account', 'CLAWOPS_API_KEY': 'synthetic-key'}
    requests, saved = [], []
    monkeypatch.setattr(tools, 'load_env', lambda: env)
    monkeypatch.setattr(tools, 'save_env', lambda key, value: saved.append((key, value)))
    def request(method, url, token, settings, body):
        requests.append((method, url, token, body))
        return 201, {'agentId': 'synthetic-agent'}
    monkeypatch.setattr(tools, 'request', request)
    monkeypatch.setattr(sys, 'argv', ['setup_service_agent.py', 'create'])
    service.main()
    assert requests == [('POST', 'https://api.claw-ops.com/v1/accounts/synthetic-account/agents',
                         'synthetic-key', service.body())]
    assert saved == [('CLAWOPS_SERVICE_AGENT_ID', 'synthetic-agent')]
