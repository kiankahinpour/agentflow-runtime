"""v0.9.0 offline contracts + live SIGKILL injection; optional VM/PG validated separately."""
import base64
import hashlib
import json
import os
import socket
import sys
import time
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentflow_runtime.api import create_app
from agentflow_runtime.metrics import render_metrics
from agentflow_runtime.store import Store
from agentflow_runtime.workflows import Workflows, normalize
from agentflow_runtime.postgres import PGConnection, PostgresStore
from agentflow_runtime.secrets_policy import ScopedSecrets, EgressPolicy
from agentflow_runtime.vm import QemuVMAdapter

TOKEN='c'*40

def test_rate_limit_is_atomic_and_shared_between_store_instances(tmp_path):
    a=Store(tmp_path/'a.db'); b=Store(tmp_path/'a.db')
    for i in range(3): assert (a if i%2==0 else b).rate_limit('abc',max_requests=3,now=120)[0]
    allowed,retry=b.rate_limit('abc',3,now=120)
    assert not allowed and retry==60
    assert a.rate_limit('abc',3,now=181)[0]


def test_api_rate_audit_and_metrics(tmp_path):
    store=Store(tmp_path/'a.db'); c=TestClient(create_app(store,TOKEN,rate_limit_per_minute=2))
    headers={'Authorization':'Bearer '+TOKEN}
    assert c.get('/api/metrics').status_code==401
    resp=c.post('/api/jobs',headers=headers,json={'prompt':'test'})
    assert resp.status_code==201
    ident=resp.json()['id']
    response=c.get('/api/metrics',headers=headers)
    assert response.status_code==200 and 'agentflow_jobs_total 1' in response.text
    assert 'agentflow_jobs_state{state="queued"} 1' in response.text
    assert c.get('/api/jobs',headers=headers).status_code==429
    audits=store.audit_records()
    assert len(audits)==1 and audits[0]['action']=='submit' and audits[0]['resource']==ident
    assert TOKEN not in str(audits)
    assert 'test' not in str(audits)


def test_tenant_actor_isolated(tmp_path):
    from agentflow_runtime.tenants import create_tenant_app
    tokens=['x'*40,'z'*40]
    users=[{'sha256':hashlib.sha256(k.encode()).hexdigest(),'role':'submitter'} for k in tokens]
    app=create_tenant_app(tmp_path,{'company':users});client=TestClient(app)
    for token in tokens:
        r=client.post('/t/company/api/jobs',headers={'Authorization':'Bearer '+token},json={'prompt':'a'})
        assert r.status_code==201
    data=Store(tmp_path/'company'/'queue.db').audit_records()
    assert len(data)==2 and len(set(row['actor'] for row in data))==2


def test_workflow_output_wiring_does_not_reprocess_injected_template(tmp_path):
    store=Store(tmp_path/'a.db');flows=Workflows(store)
    ident=flows.create([
        {'name':'first','prompt':'produce'},
        {'name':'second','prompt':'Result: {{steps.first.result}}','depends_on':['first']},
    ],'flow-one')
    assert flows.tick()==1
    first=store.claim(['echo']);assert first
    assert store.finish(first['id'],first['lease_token'],result='{{steps.third.result}}')
    assert flows.tick()==1
    second=store.claim(['echo']);assert second
    assert second['prompt']=='Result: {{steps.third.result}}'
    assert store.finish(second['id'],second['lease_token'],result='done')
    assert flows.tick()==0 and flows.get(ident)['state']=='succeeded'


def test_workflow_rejects_invalid_result_references():
    with pytest.raises(ValueError,match='direct dependency'):
        normalize([{'name':'one','prompt':'{{steps.two.result}}'}, {'name':'two','prompt':'ok'}], ['echo'])
    with pytest.raises(ValueError,match='interpolation'):
        normalize([{'name':'one','prompt':'{{evil.code}}'}], ['echo'])


def test_workflow_halts_on_large_result(tmp_path):
    s=Store(tmp_path/'a.db');w=Workflows(s)
    steps=[{'name':'one','prompt':'a'}, {'name':'two','prompt':'x'*80000+'{{steps.one.result}}','depends_on':['one']}]
    ident=w.create(steps,'large');w.tick()
    job=s.claim(['echo']);s.finish(job['id'],job['lease_token'],result='z'*40000)
    assert w.tick()==0
    assert w.get(ident)['state']=='blocked'


def test_secret_resolver_no_arbitrary_environment(monkeypatch):
    monkeypatch.setenv('ALLOWED_TEST_TOKEN','something-secret')
    b=ScopedSecrets(['ALLOWED_TEST_TOKEN'])
    assert b.get('ALLOWED_TEST_TOKEN')=='something-secret'
    with pytest.raises(PermissionError):b.get('HOME')
    with pytest.raises(ValueError):ScopedSecrets(['../../file'])
    assert len(b.fingerprint('ALLOWED_TEST_TOKEN'))==12


def test_egress_deny_private_and_unlisted(monkeypatch):
    policy=EgressPolicy(['public.example.org'])
    with pytest.raises(PermissionError):policy.resolve('http://public.example.org/')
    with pytest.raises(PermissionError):policy.resolve('https://unlisted.example.org/')
    with pytest.raises(PermissionError):policy.resolve('https://public.example.org:8443/')
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))])
    with pytest.raises(PermissionError,match='non-public'):policy.resolve('https://public.example.org/')
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))])
    assert policy.resolve('https://public.example.org/test?x=1')==('public.example.org','8.8.8.8','/test','x=1')


def test_pg_connection_pool_return_contract():
    class Pool:
        def __init__(self):self.conn=object();self.returned=[]
        def getconn(self):return self.conn
        def putconn(self,conn):self.returned.append(conn)
        def close(self):self.closed=True
    pool=Pool();store=object.__new__(PostgresStore)
    store._pool=pool
    assert store.connect().raw is pool.conn
    store.connect().close()
    assert pool.returned==[pool.conn]
    store.close();assert pool.closed


def test_metrics_only_bounded_labels(tmp_path):
    s=Store(tmp_path/'a.db');s.submit('never-leak',idem='private-key')
    output=render_metrics(s)
    assert 'never-leak' not in output and 'private-key' not in output
    assert '# TYPE agentflow_jobs_total gauge' in output
    assert 'agentflow_jobs_total 1' in output


@pytest.mark.skipif(os.name=='nt',reason='POSIX fake-QEMU contract')
def test_qemu_vm_fake_binary(tmp_path):
    image=tmp_path/'guest.qcow2';image.write_bytes(b'pretend qcow2 image for offline contract')
    fake=tmp_path/'fake-qemu'
    fake.write_text('#!'+sys.executable+'\nimport sys,base64,json\nreq=json.loads(sys.stdin.readline())\nprint("AGENTFLOW_RESULT="+base64.b64encode(req["prompt"].upper().encode()).decode())\n')
    fake.chmod(0o700)
    adapter=QemuVMAdapter(image,hashlib.sha256(image.read_bytes()).hexdigest(),qemu=str(fake),require_ready=False)
    args=adapter.command()
    assert '-net' in args and args[args.index('-net')+1]=='none'
    assert '-snapshot' in args and '-drive' in args
    assert adapter('hello vm',5)=='HELLO VM'
    with pytest.raises(ValueError):QemuVMAdapter(image,'0'*64,qemu=str(fake))


def test_local_worker_kill_leaves_uncertain():
    from tools.fault_worker_smoke import run
    assert run()['job_state']=='uncertain'


def test_manual_github_preflight():
    from tools.prepare_github import check
    assert check()['publication']=='NOT performed'
