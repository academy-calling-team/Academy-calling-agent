#!/usr/bin/env python3
"""EC2-only release controller. Existing secrets stay in root-owned env files."""
import fcntl
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

BASE = Path('/opt/team8-shared-api')
NAMES = ['team8-shared-api', 'team8-shared-worker', 'team8-shared-queue']
REPO = 'academy-calling-team/Academy-calling-agent'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def docker_json(name):
    return json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]


def probe(container, port, path='/ready'):
    script = ('import json,urllib.request; r=urllib.request.urlopen('
              + repr(f'http://127.0.0.1:{port}{path}') + ',timeout=3); assert r.status==200')
    for _ in range(40):
        if subprocess.run(['docker', 'exec', container, 'python', '-c', script],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError(f'Health check failed: {container}:{port}{path}')


def remove(name):
    subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(commit):
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('A full commit SHA is required')
    os.umask(0o077)
    BASE.mkdir(exist_ok=True)
    lock = open(BASE / 'deployment.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    statefile = BASE / 'current-release.json'
    if statefile.exists() and json.loads(statefile.read_text()).get('commit') == commit:
        for name in NAMES:
            assert docker_json(name)['State']['Running'], name
        probe(NAMES[0], 18771)
        probe(NAMES[0], 18780, '/docs')
        print(json.dumps({'status': 'already-current', 'commit': commit}))
        return
    release = BASE / 'releases' / commit
    release.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(f'https://codeload.github.com/{REPO}/tar.gz/{commit}',
                                     headers={'User-Agent': 'team8-release-controller'})
    with urllib.request.urlopen(request, timeout=60) as response:
        archive = response.read(30 * 1024 * 1024 + 1)
    if len(archive) > 30 * 1024 * 1024:
        raise RuntimeError('Release archive exceeds 30 MiB')
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        members = tar.getmembers()
        prefix = members[0].name.split('/')[0] + '/'
        for member in members:
            relative = member.name.removeprefix(prefix)
            if not relative or relative.split('/')[0] not in {'backend', 'voice', 'infra'}:
                continue
            if member.issym() or member.islnk() or '..' in Path(relative).parts:
                raise RuntimeError('Unsafe archive member')
            member.name = relative
            tar.extract(member, release, filter='data')
    api_image = f'team8-shared-api:{commit}'
    worker_image = f'team8-shared-worker:{commit}'
    logfile = BASE / f'build-{commit}.log'
    with open(logfile, 'w') as log:
        run('docker', 'build', '--memory', '256m', '-f', str(release/'infra/Dockerfile.shared-api'),
            '--build-arg', f'COMMIT_SHA={commit}', '-t', api_image, str(release), stdout=log, stderr=log)
        run('docker', 'build', '-f', str(release/'infra/Dockerfile.shared-worker'),
            '--build-arg', f'API_IMAGE={api_image}', '-t', worker_image, str(release), stdout=log, stderr=log)
    envfile = str(BASE/'runtime/api.env')
    worker_env = str(BASE/'runtime/worker.env')
    assert Path(worker_env).is_file(), 'Worker configuration is missing'
    # No CREATE/ALTER/UPDATE: reject releases requiring an unapplied DB migration.
    preflight = """from sqlalchemy import inspect
from local_runtime import local_engine
from schema import metadata
e=local_engine(); i=inspect(e)
for t in metadata.sorted_tables:
 actual={c['name'] for c in i.get_columns(t.name)}
 assert set(t.columns.keys()) <= actual, 'Missing migration: '+t.name
e.dispose()
print('Schema compatibility: OK')
"""
    run('docker', 'run', '--rm', '--network', 'team8', '--env-file', envfile,
        api_image, 'python', '-c', preflight)
    candidate = 'team8-shared-candidate'
    remove(candidate)
    try:
        run('docker','run','-d','--name',candidate,'--network','team8','--memory','192m',
            '--env-file',envfile,api_image, stdout=subprocess.DEVNULL)
        run('docker','network','connect','team8-frontend-dev',candidate)
        probe(candidate,18771)
    finally:
        remove(candidate)
    backupdir=BASE/'backups'; backupdir.mkdir(exist_ok=True)
    backupfile=backupdir/f'{int(time.time())}-{commit[:12]}.sql'
    with open(backupfile,'wb') as out:
        run('docker','exec','team8-mysql','sh','-c',
            'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump --single-transaction --no-tablespaces --set-gtid-purged=OFF -uroot team8_dev',stdout=out)
    previous={name:docker_json(name)['Config']['Image'] for name in NAMES}
    stamp=str(int(time.time()))
    renamed=[]
    run('docker','stop','-t','30',NAMES[2],stdout=subprocess.DEVNULL)
    # Let accepted mock calls finish before disconnecting the callback receiver.
    try:
        for _ in range(60):
            active=subprocess.check_output(['docker','exec',NAMES[0],'python','-c',
                "from local_runtime import local_engine; from sqlalchemy import text; e=local_engine(); c=e.connect(); print(c.execute(text(\"SELECT COUNT(*) FROM w5_inquiries WHERE status='calling'\")).scalar()); c.close(); e.dispose()"],text=True).strip()
            if active=='0': break
            time.sleep(2)
        else: raise RuntimeError('Active calls did not drain; deployment deferred')
        for name in [NAMES[1],NAMES[0]]:
            run('docker','stop','-t','30',name,stdout=subprocess.DEVNULL)
        for name in NAMES:
            old=f'{name}-previous-{stamp}'
            run('docker','rename',name,old); renamed.append((name,old))
        common=['--restart','unless-stopped','--log-opt','max-size=5m','--log-opt','max-file=3']
        run('docker','run','-d','--name',NAMES[0],'--network','team8',*common,'--memory','192m',
            '--env-file',envfile,'-p','127.0.0.1:18771:18771',api_image,stdout=subprocess.DEVNULL)
        run('docker','network','connect','team8-frontend-dev',NAMES[0])
        probe(NAMES[0],18771)
        run('docker','run','-d','--name',NAMES[1],'--network','container:'+NAMES[0],*common,
            '--memory','128m','--env-file',worker_env,'-v',
            'team8-shared-worker-receipts:/srv/repository/voice/.data',worker_image,stdout=subprocess.DEVNULL)
        probe(NAMES[0],18780,'/docs')
        run('docker','run','-d','--name',NAMES[2],'--network','container:'+NAMES[0],*common,
            '--memory','128m','--env-file',envfile,api_image,'python','run_queue.py',
            '--worker-url','http://127.0.0.1:18780',stdout=subprocess.DEVNULL)
        run('docker','exec','team8-fe-dev-https','nginx','-t',stdout=subprocess.DEVNULL)
        run('docker','exec','team8-fe-dev-https','nginx','-s','reload',stdout=subprocess.DEVNULL)
        time.sleep(2)
        for name in NAMES: assert docker_json(name)['State']['Running'], name
        with urllib.request.urlopen('https://team8-api.3.35.222.227.sslip.io/shared/ready',timeout=10) as r:
            assert r.status==200
        record={'status':'deployed','commit':commit,'api_image':api_image,'worker_image':worker_image,
                'previous_images':previous,'previous_containers':dict(renamed),'backup':str(backupfile),
                'deployed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
        tmp=statefile.with_suffix('.tmp'); tmp.write_text(json.dumps(record,indent=2)); tmp.replace(statefile)
        installed=BASE/'deploy/deploy.py'
        updated=installed.with_suffix('.next')
        shutil.copy2(release/'infra/deploy-shared-api.py',updated)
        updated.chmod(0o700); updated.replace(installed)
        # Keep one stopped generation for rollback; its network namespace is preserved.
        for name in NAMES:
            output=subprocess.check_output(['docker','ps','-a','--filter',f'name=^{name}-previous-','--format','{{.Names}}'],text=True)
            keep=dict(renamed)[name]
            for old in output.splitlines():
                if old!=keep: remove(old)
        print(json.dumps(record))
    except BaseException:
        for name,old in reversed(renamed): remove(name)
        for name,old in renamed: run('docker','rename',old,name)
        for name in NAMES: run('docker','start',name,stdout=subprocess.DEVNULL)
        subprocess.run(['docker','exec','team8-fe-dev-https','nginx','-s','reload'],capture_output=True)
        raise


if __name__=='__main__':
    main(sys.argv[1])
