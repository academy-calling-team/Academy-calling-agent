"""Exercise real child exit paths with fake controllers; never contact the server."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import stat
import time
import urllib.error

import pytest

INFRA = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('deployment_history', INFRA / 'deploy-observability.py')
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)
SHA = 'a' * 40


@pytest.fixture(autouse=True)
def restore_umask():
    mask = os.umask(0o077)
    yield
    os.umask(mask)


def run_fake(tmp_path, source, collector=lambda: {'public_ready': {'http_status': 200}}):
    child = tmp_path / 'fake.py'
    child.write_text(source, encoding='utf-8')
    result = history.deploy(SHA, base=tmp_path, controller=child, collector=collector,
                            run_id='123', run_attempt='2')
    records = list((tmp_path / 'deployment-history').glob('*.json'))
    return result, [json.loads(path.read_text()) for path in records]


def test_success_records_both_snapshots_and_github_link(tmp_path):
    code, records = run_fake(tmp_path, "print('[deploy-stage] complete')")
    item = records[0]
    assert code == 0 and item['status'] == 'success'
    assert item['stage'] == 'complete' and item['before'] == item['after']
    assert item['github_url'].endswith('/123/attempts/2')
    assert item['finished_at'] >= item['started_at']
    if os.name == 'posix':
        directory = tmp_path / 'deployment-history'
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(next(directory.glob('*.json')).stat().st_mode) == 0o600


def test_dns_failure_preserves_failed_phase_and_post_rollback_version(tmp_path):
    source = """import sys
print('[deploy-stage] public_ready')
print('[deploy-stage] rollback')
print('socket.gaierror: [Errno -2] Name or service not known')
print('urllib.error.URLError: <urlopen error [Errno -2] Name or service not known>')
sys.exit(7)
"""
    code, records = run_fake(tmp_path, source, lambda: {'internal_version': {'commit': 'b' * 40}})
    item = records[0]
    assert code == 7 and item['status'] == 'failed'
    assert item['failed_stage'] == 'public_ready'
    assert {'error_type': 'gaierror', 'errno': -2} in item['errors']
    assert item['after']['internal_version']['commit'] == 'b' * 40


def test_early_failure_is_recorded_without_overwriting_another_attempt(tmp_path):
    code, records = run_fake(tmp_path, "raise ValueError('bad input')")
    assert code != 0 and records[0]['errors'] == [{'error_type': 'ValueError'}]
    _, records = run_fake(tmp_path, "print('[deploy-stage] complete')")
    assert len(records) == 2 and len({item['id'] for item in records}) == 2


def test_arbitrary_output_and_error_messages_are_never_persisted(tmp_path, capsys):
    secret = 'PRIVATE_TEST_VALUE'
    code, records = run_fake(tmp_path, "print('" + secret + "'); raise RuntimeError('" + secret + "')")
    assert code != 0
    assert secret not in json.dumps(records)
    assert secret not in capsys.readouterr().out
    assert records[0]['errors'] == [{'error_type': 'RuntimeError'}]


@pytest.mark.parametrize('commit,run_id', [('../bad', ''), ('a' * 40, '$(bad)')])
def test_invalid_metadata_never_starts_controller(tmp_path, commit, run_id):
    with pytest.raises(ValueError):
        history.deploy(commit, base=tmp_path, run_id=run_id)
    assert not (tmp_path / 'deployment-history').exists()


def test_snapshot_failure_still_finishes_failure_record(tmp_path):
    def broken():
        raise OSError('PRIVATE_TEST_VALUE')
    code, records = run_fake(tmp_path, "raise AssertionError('must not execute')", broken)
    assert code != 0 and records[0]['status'] == 'failed'
    assert records[0]['after'] == {'snapshot_error': 'OSError'}
    assert 'PRIVATE_TEST_VALUE' not in json.dumps(records)


def test_retention_removes_only_expired_history_files(tmp_path):
    for name in ('old.json', 'keep.json', 'unrelated.log'):
        (tmp_path / name).write_text('{}')
    old_time = time.time() - 91 * 86400
    os.utime(tmp_path / 'old.json', (old_time, old_time))
    history.prune(tmp_path)
    assert not (tmp_path / 'old.json').exists()
    assert (tmp_path / 'keep.json').exists() and (tmp_path / 'unrelated.log').exists()


def test_snapshot_allowlists_endpoint_payload(monkeypatch):
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, limit):
            return json.dumps({'ready': True, 'database': 'ok', 'queue': 'ok',
                               'commit': SHA, 'transcript': 'PRIVATE_TEST_VALUE'}).encode()
    monkeypatch.setattr(history.urllib.request, 'urlopen', lambda *a, **k: Response())
    result = history.http_probe('http://unused/ready', 'ready')
    assert result['ready'] is True and result['database'] == 'ok'
    assert 'PRIVATE_TEST_VALUE' not in json.dumps(result)
    assert history.http_probe('http://unused/version', 'commit')['commit'] == SHA


def test_snapshot_dns_exception_is_classified_without_raw_message(monkeypatch):
    import socket
    def failed(*a, **k):
        raise urllib.error.URLError(socket.gaierror(-2, 'PRIVATE_TEST_VALUE'))
    monkeypatch.setattr(history.urllib.request, 'urlopen', failed)
    result = history.http_probe('http://unused/ready', 'ready')
    assert result['error_type'] == 'gaierror' and result['errno'] == -2
    assert 'PRIVATE_TEST_VALUE' not in json.dumps(result)


def test_container_probe_does_not_request_environment_or_application_logs(monkeypatch):
    def command(args):
        assert args[:3] == ['docker', 'inspect', '--format']
        assert 'Env' not in args[3] and '.State.Error' not in args[3]
        return 0, 'true false 0 2 2026-11-01T00:00:00Z 0001-01-01T00:00:00Z team8-shared-api:' + SHA
    monkeypatch.setattr(history, 'command', command)
    result = history.container_probe('team8-shared-api')
    assert result['running'] is True and result['restart_count'] == 2


def test_old_controller_error_has_public_ready_hint():
    record = dict(stage='starting', events=[], errors=[], checks={})
    history.observe_line(record, "with urllib.request.urlopen('https://" + history.HOST + "/shared/ready',timeout=10) as r:")
    assert record['failure_stage_hint'] == 'public_ready'


def test_document_uses_in_place_version_update_and_validated_parameters():
    template = json.loads((INFRA / 'shared-api-autodeploy.cfn.json').read_text())
    document = template['Resources']['DeployDocument']['Properties']
    assert document['UpdateMethod'] == 'NewVersion'
    assert document['Content']['parameters']['GitHubRunId']['allowedPattern'] == '^[0-9]{0,20}$'
    command = document['Content']['mainSteps'][0]['inputs']['runCommand'][1]
    assert 'deploy-observability.py deploy' in command


def test_controller_markers_use_known_names():
    tree = ast.parse((INFRA / 'deploy-shared-api.py').read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'stage':
            assert node.args[0].value in history.STAGES
