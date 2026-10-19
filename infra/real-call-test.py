#!/usr/bin/env python3
"""Root-only interactive setup on the existing EC2 host; never puts secrets in commands.

Run from an interactive SSH/Session Manager shell. Hidden prompts send values to
root-owned env files and container stdin, without echoing them or using SSM commands.
"""
import argparse
import fcntl
import getpass
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

BASE=Path('/opt/team8-shared-api')
NAMES=['team8-shared-api','team8-shared-worker','team8-shared-queue']
SETTING_KEYS=['CLAWOPS_API_KEY','CLAWOPS_ACCOUNT_ID','CLAWOPS_SERVICE_AGENT_ID','CLAWOPS_FROM_NUMBER']

def docker(*args):
    # Suppress stderr as container failures can include submitted values.
    r=subprocess.run(['docker',*args],capture_output=True,text=True)
    if r.returncode:raise RuntimeError('Container operation failed; inspect privately on server')
    return r.stdout

def db(action,**values):
    r=subprocess.run(['docker','exec','-i',NAMES[0],'python','real_test_setup.py'],
        input=json.dumps(dict(action=action,**values)),capture_output=True,text=True)
    if r.returncode:raise RuntimeError('Database setup failed: check account, terms agreement and test academy privately')
    return json.loads(r.stdout)

def read_env(path):
    return dict(line.split('=',1) for line in path.read_text().splitlines()
                if line.strip() and not line.startswith('#') and '=' in line)

def write_env(path,values):
    if any('\n' in v or '\r' in v for v in values.values()):raise ValueError('Multiline settings are not supported')
    tmp=path.with_suffix('.next');tmp.write_text(''.join(k+'='+v+'\n' for k,v in values.items()))
    tmp.chmod(0o600);tmp.replace(path)

def controller():
    spec=importlib.util.spec_from_file_location('team8_deploy',BASE/'deploy/deploy.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def recreate():
    """Replace all three containers to reload env; keep one prior generation for recovery."""
    ctl=controller(); stamp=str(time.time_ns()); renamed=[]
    images={n:json.loads(docker('inspect',n))[0]['Config']['Image'] for n in NAMES}
    common=['--restart','unless-stopped','--log-opt','max-size=5m','--log-opt','max-file=3']
    try:
        for name in reversed(NAMES):docker('stop','-t','30',name)
        for name in NAMES:
            old=name+'-config-'+stamp;docker('rename',name,old);renamed.append((name,old))
        docker('run','-d','--name',NAMES[0],'--network','team8',*common,'--memory','192m',
            '--env-file',str(BASE/'runtime/api.env'),'-p','127.0.0.1:18771:18771',images[NAMES[0]])
        docker('network','connect','team8-frontend-dev',NAMES[0]);ctl.probe(NAMES[0],18771)
        docker('run','-d','--name',NAMES[1],'--network','container:'+NAMES[0],*common,'--memory','128m',
            '--env-file',str(BASE/'runtime/worker.env'),'-v',
            'team8-shared-worker-receipts:/srv/repository/voice/.data',images[NAMES[1]])
        ctl.probe(NAMES[0],18780,'/docs')
        docker('run','-d','--name',NAMES[2],'--network','container:'+NAMES[0],*common,'--memory','128m',
            '--env-file',str(BASE/'runtime/api.env'),images[NAMES[2]],'python','run_queue.py',
            '--worker-url','http://127.0.0.1:18780')
        docker('exec','team8-fe-dev-https','nginx','-s','reload')
        time.sleep(2)
        if not all(json.loads(docker('inspect',n))[0]['State']['Running'] for n in NAMES):
            raise RuntimeError('Container did not remain running')
        # Remove only older stopped config generations. Preserve the one just stopped.
        for name,keep in renamed:
            for old in docker('ps','-a','--filter','name=^'+name+'-config-','--format','{{.Names}}').splitlines():
                if old!=keep:docker('rm',old)
    except BaseException:
        # Fail closed: never restart a previous generation that could still allow calls.
        for n in NAMES:subprocess.run(['docker','stop','-t','5',n],capture_output=True)
        raise RuntimeError('Configuration reload failed. Shared services stopped; repair with real calls disabled.') from None

def hidden(label):
    if not sys.stdin.isatty():raise ValueError('Use an interactive terminal for private settings')
    value=getpass.getpass(label+': ').strip()
    if not value or '\n' in value or '\r' in value:raise ValueError('A single nonempty value is required')
    return value

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['status','prepare','configure','enable','disable'])
    action=parser.parse_args().action
    if os.geteuid()!=0:raise ValueError('Run with sudo on the EC2 host')
    os.umask(0o077)
    with open(BASE/'deployment.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        api_path=BASE/'runtime/api.env';worker_path=BASE/'runtime/worker.env'
        api=read_env(api_path);worker=read_env(worker_path)
        state=db('status')
        if action=='status':
            print(json.dumps(dict(**state,api_enabled=api.get('REAL_CALLS_ENABLED')=='1',
                worker_enabled=worker.get('REAL_CALLS_ENABLED')=='1',
                settings_prepared=all(worker.get(k) for k in SETTING_KEYS),
                test_account_prepared=bool(api.get('REAL_TEST_INQUIRER_ID')))));return
        if action=='prepare':print(json.dumps(db('prepare')));return
        # Do not interrupt in-flight calls or silently revive queued work after enabling.
        if state['active_calls'] or (action in ['configure','enable'] and state['pending_inquiries']):
            raise ValueError('Wait for active/pending inquiries to finish before changing call settings')
        if action=='configure':
            if api.get('REAL_CALLS_ENABLED')=='1' or worker.get('REAL_CALLS_ENABLED')=='1':
                raise ValueError('Disable real calls before configuring')
            login=hidden('Existing frontend test login name')
            owner=db('owner',login_name=login)['owner']
            number=hidden('Receiver mobile number (+8210...)')
            settings={k:hidden(k) for k in SETTING_KEYS}
            # A single canonical destination is used at all three gates.
            import re
            number=re.sub(r'[\s()-]','',number)
            if re.fullmatch('010[0-9]{8}',number):number='+82'+number[1:]
            if not re.fullmatch(r'\+8210[0-9]{8}',number):raise ValueError('One Korean mobile number required')
            db('configure',phone=number)
            api.update(REAL_TEST_INQUIRER_ID=owner,REAL_CALL_ALLOWED_TO=number)
            worker.update(settings,REAL_CALL_ALLOWED_TO=number)
            api.pop('REAL_CALLS_ENABLED',None);worker.pop('REAL_CALLS_ENABLED',None)
        elif action=='enable':
            if not sys.stdin.isatty() or input('Receiver is ready NOW; type ENABLE: ')!='ENABLE':
                raise ValueError('Receiver readiness confirmation required')
            if not (state['phone_configured'] and api.get('REAL_TEST_INQUIRER_ID') and
                    api.get('REAL_CALL_ALLOWED_TO')==worker.get('REAL_CALL_ALLOWED_TO') and
                    api.get('REAL_CALL_ALLOWED_TO') and all(worker.get(k) for k in SETTING_KEYS)):
                raise ValueError('Complete configure first')
            api['REAL_CALLS_ENABLED']='1';worker['REAL_CALLS_ENABLED']='1'
        else:
            for values in [api,worker]:
                for key in ['REAL_CALLS_ENABLED','REAL_CALL_ALLOWED_TO','REAL_TEST_INQUIRER_ID']:
                    values.pop(key,None)
            db('clear')
        write_env(api_path,api);write_env(worker_path,worker)
        try:recreate()
        except BaseException:
            # Ensure a later manual recreation cannot accidentally enable dialing.
            api.pop('REAL_CALLS_ENABLED',None);worker.pop('REAL_CALLS_ENABLED',None)
            write_env(api_path,api);write_env(worker_path,worker);raise
        print(json.dumps({'status':action+'d','real_calls_enabled':action=='enable','containers_recreated':True}))

if __name__=='__main__':
    try:main()
    except Exception as error:
        print(str(error),file=sys.stderr);sys.exit(1)
