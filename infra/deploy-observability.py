#!/usr/bin/env python3
"""Private, bounded deployment history. Never persist child output or app data."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = Path('/opt/team8-shared-api')
HOST = 'team8-api.3.35.222.227.sslip.io'
NAMES = ('team8-shared-api', 'team8-shared-worker', 'team8-shared-queue', 'team8-fe-dev-https')
STAGES = {'starting', 'lock', 'already_current', 'download', 'build_api', 'build_worker',
          'schema', 'candidate', 'backup', 'drain', 'replace', 'api_ready', 'worker_ready',
          'nginx', 'public_ready', 'save_release', 'cleanup', 'complete', 'rollback'}
ERRORS = ('gaierror', 'TimeoutError', 'HTTPError', 'URLError', 'ConnectionRefusedError',
          'ConnectionResetError', 'SSLCertVerificationError', 'SSLError',
          'CalledProcessError', 'AssertionError', 'RuntimeError', 'ValueError',
          'FileNotFoundError', 'PermissionError', 'BlockingIOError', 'OSError')
KST = timezone(timedelta(hours=9))


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def error_info(exc):
    reason = getattr(exc, 'reason', exc)
    result = {'error_type': type(reason).__name__}
    if isinstance(getattr(reason, 'errno', None), int):
        result['errno'] = reason.errno
    if isinstance(exc, urllib.error.HTTPError):
        result['http_status'] = exc.code
    return result


def command(args, timeout=3):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except Exception as exc:
        return -1, type(exc).__name__


def http_probe(url, field):
    start = time.monotonic()
    result = {}
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            result['http_status'] = response.status
            data = json.loads(response.read(8192))
            # Explicit value allowlist; never record arbitrary responses.
            if field == 'commit':
                value = data.get('commit')
                if isinstance(value, str) and re.fullmatch('[0-9a-f]{40}', value):
                    result['commit'] = value
            else:
                for key in ('ready', 'database', 'queue'):
                    value = data.get(key)
                    if type(value) is bool or (isinstance(value, str) and value in ('ok', 'error', 'ready')):
                        result[key] = value
    except Exception as exc:
        result.update(error_info(exc))
    result['elapsed_ms'] = round((time.monotonic() - start) * 1000)
    return result


def dns_probe():
    code, output = command(['getent', 'ahostsv4', HOST])
    addresses = set()
    if code == 0:
        for line in output.splitlines():
            try:
                addresses.add(str(ipaddress.ip_address(line.split()[0])))
            except (ValueError, IndexError):
                pass
    return {'exit_code': code, 'addresses': sorted(addresses)}


def container_probe(name):
    fmt = ('{{json .State.Running}} {{json .State.OOMKilled}} {{.State.ExitCode}} '
           '{{.RestartCount}} {{.State.StartedAt}} {{.State.FinishedAt}} {{.Config.Image}}')
    code, output = command(['docker', 'inspect', '--format', fmt, name])
    parts = output.split()
    if code != 0 or len(parts) != 7:
        return {'inspect_exit_code': code}
    try:
        result = dict(running=parts[0] == 'true', oom_killed=parts[1] == 'true',
                      exit_code=int(parts[2]), restart_count=int(parts[3]))
        for key, value in zip(('started_at', 'finished_at', 'image'), parts[4:]):
            if re.fullmatch(r'[a-zA-Z0-9_:./+@-]{1,200}', value):
                result[key] = value
        return result
    except ValueError:
        return {'inspect_exit_code': code, 'parse_error': True}


def snapshot():
    result = {'observed_at': now()}
    try:
        disk = shutil.disk_usage(BASE)
        result['disk'] = {'free_bytes': disk.free, 'total_bytes': disk.total}
        result['load'] = list(os.getloadavg())
        result['uptime_seconds'] = float(Path('/proc/uptime').read_text().split()[0])
        memory = dict(re.findall(r'^(MemTotal|MemAvailable):\s+(\d+)',
                                 Path('/proc/meminfo').read_text(), re.M))
        result['memory_kib'] = {key: int(value) for key, value in memory.items()}
    except Exception as exc:
        result['host_metrics_error'] = type(exc).__name__
    jobs = {'dns': (dns_probe, ())}
    for scope, origin in (('internal', 'http://127.0.0.1:18771'),
                          ('public', 'https://' + HOST + '/shared')):
        for endpoint in ('ready', 'version'):
            jobs[scope + '_' + endpoint] = (http_probe, (origin + '/' + endpoint,
                                                        'commit' if endpoint == 'version' else 'ready'))
    for name in NAMES:
        jobs[name] = (container_probe, (name,))
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {key: pool.submit(func, *args) for key, (func, args) in jobs.items()}
        for key, future in futures.items():
            try:
                result[key] = future.result()
            except Exception as exc:
                result[key] = error_info(exc)
    return result


def save_record(directory, record):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    target = directory / (record['id'] + '.json')
    temp = target.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(target)


def prune(directory, days=90, count=500):
    cutoff = time.time() - days * 86400
    files = sorted(directory.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for index, path in enumerate(files):
        # Recent in-progress runs are retained even with overlapping manual calls.
        if path.stat().st_mtime < cutoff or (index >= count and path.stat().st_mtime < time.time() - 3600):
            path.unlink()
    for path in directory.glob('*.tmp'):
        if path.stat().st_mtime < time.time() - 86400:
            path.unlink()


def observe_line(record, line):
    # Only known stage tokens and error identifiers survive into history.
    line = line[:8192]
    match = re.fullmatch(r'\[deploy-stage\] ([a-z_]+)\s*', line)
    if match and match[1] in STAGES:
        if match[1] == 'rollback':
            record['failed_stage'] = record['stage']
        record['stage'] = match[1]
        if len(record['events']) < 100:
            record['events'].append({'at': now(), 'stage': match[1]})
        return True
    if 'Schema compatibility: OK' == line.strip():
        record['checks']['schema'] = 'passed'
    if 'nginx:' in line and 'test is successful' in line:
        record['checks']['nginx'] = 'passed'
    # Existing controllers have no stage markers; identify the fixed readiness line.
    if HOST + '/shared/ready' in line:
        record['failure_stage_hint'] = 'public_ready'
    for name in ERRORS:
        if re.match(r'^(?:[A-Za-z_][\w]*\.)*' + name + r':', line):
            item = {'error_type': name}
            number = re.search(r'\[Errno (-?\d+)\]', line)
            if number:
                item['errno'] = int(number[1])
            if item not in record['errors'] and len(record['errors']) < 20:
                record['errors'].append(item)
    return False


def deploy(commit, base=BASE, collector=snapshot, controller=None, run_id='', run_attempt=''):
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('A full commit SHA is required')
    if not re.fullmatch('[0-9]{0,20}', run_id) or not re.fullmatch('[0-9]{0,5}', run_attempt):
        raise ValueError('Invalid GitHub run metadata')
    os.umask(0o077)
    directory = base / 'deployment-history'
    record = dict(id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:12],
                  schema_version=1, kind='deployment', commit=commit, started_at=now(),
                  status='running', stage='starting', events=[], errors=[], checks={})
    if run_id:
        record['github_url'] = ('https://github.com/academy-calling-team/Academy-calling-agent/actions/runs/'
                                + run_id + ('/attempts/' + run_attempt if run_attempt else ''))
    # A writable history is a precondition: do not silently deploy without a record.
    save_record(directory, record)
    start = time.monotonic()
    child = None
    interrupted = []
    old_handlers = {}

    def handle_signal(number, frame):
        interrupted.append(number)
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGINT)  # Controller catches BaseException and rolls back.

    try:
        for number in (signal.SIGTERM, signal.SIGINT):
            old_handlers[number] = signal.signal(number, handle_signal)
        prune(directory)
        record['before'] = collector()
        save_record(directory, record)
        if interrupted:
            raise InterruptedError()
        child = subprocess.Popen([sys.executable, '-u', str(controller or base / 'deploy/deploy.py'), commit],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 encoding='utf-8', errors='replace', start_new_session=True)
        # Bounded reads prevent unbounded log lines from exhausting memory.
        while True:
            line = child.stdout.readline(8192)
            if not line:
                break
            if observe_line(record, line):
                try:
                    save_record(directory, record)
                except OSError as exc:
                    # Let the existing controller finish/roll back if storage fills mid-run.
                    record['logging_error'] = error_info(exc)
                print(line.strip(), flush=True)
        code = child.wait()
        record['exit_code'] = code
        record['status'] = 'interrupted' if interrupted else ('success' if code == 0 else 'failed')
        if interrupted:
            record['exit_code'] = 1
    except Exception as exc:
        record['status'] = 'interrupted' if interrupted else 'failed'
        record['errors'].append(error_info(exc))
        record['exit_code'] = 1
    finally:
        if record['status'] != 'success':
            record.setdefault('failed_stage', record.get('failure_stage_hint', record['stage']))
        record['finished_at'] = now()
        record['duration_seconds'] = round(time.monotonic() - start, 2)
        try:
            record['after'] = collector()
        except Exception as exc:
            record['after'] = {'snapshot_error': type(exc).__name__}
        for number, handler in old_handlers.items():
            signal.signal(number, handler)
        save_record(directory, record)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    return record['exit_code'] if record['exit_code'] > 0 else (1 if record['exit_code'] < 0 else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('deploy')
    p.add_argument('commit')
    p.add_argument('--run-id', default='')
    p.add_argument('--run-attempt', default='')
    sub.add_parser('history')
    p = sub.add_parser('show')
    p.add_argument('id')
    sub.add_parser('status')
    args = parser.parse_args()
    if args.action == 'deploy':
        return deploy(args.commit, run_id=args.run_id, run_attempt=args.run_attempt)
    if args.action == 'status':
        print(json.dumps(snapshot(), indent=2, ensure_ascii=False))
    elif args.action == 'show':
        if not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{12}', args.id):
            parser.error('Invalid history ID')
        print((BASE / 'deployment-history' / (args.id + '.json')).read_text())
    else:
        for path in sorted((BASE / 'deployment-history').glob('*.json'), reverse=True)[:30]:
            data = json.loads(path.read_text())
            local = datetime.fromisoformat(data['started_at']).astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')
            status = data['status']
            if status == 'running' and path.stat().st_mtime < time.time() - 1800:
                status = 'unfinished (check SSM)'
            print(f"{local}  {status:12}  {data['commit'][:12]}  {data['id']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
