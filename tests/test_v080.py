"""v0.8 offline contract tests; no claims about a real Docker/PG daemon."""
import os
import re
import threading
import time
import sys
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentflow_runtime import __version__
from agentflow_runtime.store import Store
from agentflow_runtime.api import create_app
from agentflow_runtime.worker import Worker
from agentflow_runtime.postgres import PGConnection, _placeholders, PostgresStore, LOCK_KEY
from agentflow_runtime.sandbox import DockerSandboxAdapter, secure_docker_args

PINNED='example.com/agent/worker@sha256:'+'a'*64


def test_sandbox_restrictive_args():
    args=secure_docker_args('/usr/bin/docker',PINNED,['agent','-'], 'agentflow-'+'f'*32)
    assert args[:4]==['/usr/bin/docker','run','--rm','--pull=never']
    for opt,value in [('--network=none',None),('--read-only',None),('--cap-drop=ALL',None),('--security-opt=no-new-privileges',None),('--user=65534:65534',None),('--pull=never',None),('--memory','256m'),('--pids-limit=64',None)]:
        assert opt in args
        if value:assert args[args.index(opt)+1]==value
    assert '--privileged' not in args and '--volume' not in args and '-v' not in args
    assert '--mount' not in args
    assert args[-3:]==[PINNED,'agent','-']


@pytest.mark.parametrize('image', ['ubuntu:latest','image','docker.io/bad@sha256:'+'q'*64,'image@sha256:'+'0'*63])
def test_unpinned_sandbox_rejected(image):
    with pytest.raises(ValueError):secure_docker_args('docker',image,['cat'],'agentflow-'+'0'*32)



def test_registry_port_in_pinned_image():
    secure_docker_args('docker','registry.example.org:5000/repo/image@sha256:'+'f'*64,['cat'],'agentflow-'+'0'*32)


@pytest.mark.skipif(os.name=='nt',reason='POSIX mock executable')
def test_fake_docker_cli_echo(tmp_path):
    """Test process contract with fake client; not a Docker isolation test."""
    fake=tmp_path/'docker-fake'
    fake.write_text('#!/usr/bin/env python3\nimport sys\nif sys.argv[1]=="run":\n print(sys.stdin.read(),end="")\nelse:\n print("unused")\n')
    fake.chmod(0o700)
    adapter=DockerSandboxAdapter(PINNED,['cat'],docker=str(fake))
    assert adapter('hello sandbox',5)=='hello sandbox'

def test_sandbox_rejects_bad_resources():
    with pytest.raises(ValueError):secure_docker_args('docker',PINNED,['cat'],'agentflow-'+'0'*32,cpus=100)
    with pytest.raises(ValueError):secure_docker_args('docker',PINNED,['cat'],'agentflow-'+'0'*32,memory_mb=8)
    with pytest.raises(ValueError):secure_docker_args('docker',PINNED,[], 'agentflow-'+'0'*32)


def test_postgres_placeholder_conversion():
    assert _placeholders('SELECT id FROM jobs WHERE state=? AND adapter=?') == 'SELECT id FROM jobs WHERE state=%s AND adapter=%s'


def test_pg_connection_contract():
    class DB:
        def __init__(self):self.sql=[];self.commits=0;self.rollbacks=0;self.closed=False
        def execute(self,sql,params=()):self.sql.append((sql,params));return self
        def fetchone(self):return {'state':'queued'}
        def commit(self):self.commits+=1
        def rollback(self):self.rollbacks+=1
        def close(self):self.closed=True
    fake=DB();pg=PGConnection(fake)
    assert pg.execute('SELECT * FROM jobs WHERE id=?',('hi',)).fetchone()=={'state':'queued'}
    assert fake.sql==[('SELECT * FROM jobs WHERE id=%s',('hi',))]
    pg.commit();pg.rollback();pg.close()
    assert (fake.commits,fake.rollbacks,fake.closed)==(1,1,True)


def test_pg_transaction_lock_and_rollback():
    calls=[]
    class Connection:
        def execute(self,q,args=()):calls.append(('exec',q,args))
        def commit(self):calls.append(('commit',))
        def rollback(self):calls.append(('rollback',))
        def close(self):calls.append(('close',))
    pg=object.__new__(PostgresStore)
    pg.connect=lambda:Connection()
    with pg.tx() as c:c.execute('work')
    assert calls[0]==('exec','SELECT pg_advisory_xact_lock(?)',(LOCK_KEY,))
    assert ('commit',) in calls and ('close',) in calls
    calls.clear()
    with pytest.raises(ZeroDivisionError):
        with pg.tx():1/0
    assert ('rollback',) in calls


def test_readiness_api_and_sandbox_approval(tmp_path):
    store=Store(tmp_path/'queue.db')
    app=create_app(store,'s'*32,external_catalog=['sandbox'])
    client=TestClient(app);auth={'Authorization':'Bearer '+'s'*32}
    assert client.get('/health/ready').json()=={'status':'ready'}
    r=client.get('/api/runtime',headers=auth).json()
    assert r=={'version':__version__,'backend':'sqlite','distributed_coordination':False,'hostile_multi_tenant_execution':False}
    assert any(a['name']=='sandbox' for a in client.get('/api/adapters',headers=auth).json())
    response=client.post('/api/jobs',headers=auth,json={'adapter':'sandbox','prompt':'safe'})
    assert response.status_code==201
    assert store.get(response.json()['id'])['state']=='waiting_approval'


def test_concurrent_sqlite_claim_fencing(tmp_path):
    """Consistency invariant shared with PG, not a PostgreSQL integration test."""
    db=tmp_path/'x.db';s=Store(db)
    keys=[s.submit(f'{n}') for n in range(70)]
    done=[]
    def run():
        worker=Worker(Store(db),{'echo':lambda p,t:p})
        while worker.once():done.append(1)
    threads=[threading.Thread(target=run) for _ in range(4)]
    for t in threads:t.start()
    for t in threads:t.join(timeout=30)
    assert all(not t.is_alive() for t in threads)
    assert len(done)==70
    assert all(s.get(k)['state']=='succeeded' and s.get(k)['attempts']==1 for k in keys)


@pytest.mark.skipif(not os.getenv('AGENTFLOW_TEST_POSTGRES_DSN'),reason='requires live PostgreSQL DSN')
def test_live_postgres_multi_instance_contract():
    """Run against disposable dedicated PostgreSQL database in CI; never production."""
    import uuid
    from agentflow_runtime.workflows import Workflows
    pg=PostgresStore(os.environ['AGENTFLOW_TEST_POSTGRES_DSN'])
    key='v080-'+uuid.uuid4().hex
    a=pg.submit('a',idem=key); assert a==pg.submit('a',idem=key)
    claimed=pg.claim(['echo']);assert claimed is not None
    assert pg.finish(claimed['id'],claimed['lease_token'],result='ok')
    assert pg.get(claimed['id'])['state']=='succeeded'
    flows=Workflows(pg)
    wf=flows.create([{'name':'first','prompt':'x'},{'name':'last','prompt':'y','depends_on':['first']}],key+'-wf')
    assert wf==flows.create([{'name':'first','prompt':'x'},{'name':'last','prompt':'y','depends_on':['first']}],key+'-wf')
    assert flows.tick()>=1
    assert flows.get(wf)['state']=='active'
    worker=Worker(pg,{'echo':lambda p,t:p},workflows=True)
    worker.once()
    worker.once()
    flows.tick()
    assert flows.get(wf)['state']=='succeeded'


def test_postgres_requires_optional_driver_when_absent():
    import importlib.util
    if importlib.util.find_spec('psycopg') is None:
        with pytest.raises(RuntimeError,match='psycopg|postgres'):
            PostgresStore('postgresql://example.invalid/agentflow')


def test_compose_safe_defaults():
    compose=(Path(__file__).resolve().parents[1]/'compose.yaml').read_text()
    assert '127.0.0.1:8787:8787' in compose
    assert '/var/run/docker.sock' not in compose
    assert 'agentflow worker' not in compose or 'external' not in compose
    assert 'internal: true' in compose
