import os
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from agentflow_runtime import Store, Conflict, Worker
from agentflow_runtime.worker import ExecutionStopped
from agentflow_runtime.adapters import codex_adapter
from agentflow_runtime.api import create_app

@pytest.fixture
def store(tmp_path):return Store(tmp_path/'jobs.db')

def test_cancel_running_idempotent_and_fenced(store):
    ident=store.submit('work',max_attempts=2);job=store.claim(['echo'])
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _:store.cancel(ident),range(8)))==['cancel_requested']*8
    assert store.renew(ident,job['lease_token'])=='cancel_requested'
    assert not store.finish(ident,'wrong',stopped=True)
    assert store.finish(ident,job['lease_token'],stopped=True)
    assert store.get(ident)['state']=='cancelled'
    assert store.claim(['echo']) is None
    assert [x['kind'] for x in store.events(ident)].count('cancel_requested')==1

@pytest.mark.parametrize('error',[None,'failed'])
def test_cancel_race_is_uncertain(store,error):
    ident=store.submit('task',max_attempts=2);job=store.claim(['echo']);store.cancel(ident)
    assert store.finish(ident,job['lease_token'],result='late',error=error)
    assert store.get(ident)['state']=='uncertain'
    assert store.claim(['echo']) is None

def test_expired_cancel_is_uncertain(store):
    ident=store.submit('task');job=store.claim(['echo']);store.cancel(ident)
    with store.tx() as c:c.execute('UPDATE jobs SET lease_until=0 WHERE id=?',(ident,))
    assert store.recover_expired()==1
    assert store.get(ident)['state']=='uncertain'
    assert not store.finish(ident,job['lease_token'],stopped=True)

def test_cooperative_worker_cancel(store):
    started=threading.Event()
    def adapter(prompt,timeout,*,cancel_event):
        started.set();assert cancel_event.wait(3);raise ExecutionStopped()
    adapter.supports_cancellation=True
    ident=store.submit('task')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(Worker(store,{'echo':adapter}).once)
        assert started.wait(2);store.cancel(ident);assert future.result(5)
    assert store.get(ident)['state']=='cancelled'

def test_legacy_adapter_cannot_claim_stop(store):
    started=threading.Event();release=threading.Event()
    def adapter(p,t):started.set();release.wait(3);return p
    ident=store.submit('task')
    with ThreadPoolExecutor(max_workers=1) as pool:
        f=pool.submit(Worker(store,{'echo':adapter}).once)
        assert started.wait(2);store.cancel(ident);release.set();assert f.result(5)
    assert store.get(ident)['state']=='uncertain'

def test_lost_lease_interrupts_cooperative_adapter(store):
    started=threading.Event()
    def adapter(p,t,*,cancel_event):
        started.set();assert cancel_event.wait(3);raise ExecutionStopped()
    adapter.supports_cancellation=True
    ident=store.submit('task')
    with ThreadPoolExecutor(max_workers=1) as pool:
        f=pool.submit(Worker(store,{'echo':adapter}).once)
        assert started.wait(2)
        with store.tx() as c:c.execute('UPDATE jobs SET lease_until=0 WHERE id=?',(ident,))
        store.recover_expired();assert f.result(5)
    assert store.get(ident)['state']=='uncertain'

def test_api_cancel_state_and_auth(store):
    token='local-test-token-0123456789';client=TestClient(create_app(store,token))
    ident=store.submit('work');store.claim(['echo']);url=f'/api/jobs/{ident}/cancel'
    assert client.post(url).status_code==401
    assert client.post(url,headers={'Authorization':'Bearer '+token}).json()['state']=='cancel_requested'

def test_migration_legacy_preserves_jobs(store):
    ident=store.submit('old')
    with store.tx() as c:c.execute('DROP INDEX active_leases');c.execute('PRAGMA user_version=0')
    migrated=Store(store.path)
    assert migrated.get(ident)['prompt']=='old'
    with migrated.tx() as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==6
        assert c.execute("SELECT name FROM sqlite_master WHERE name='active_leases'").fetchone()

def test_migration_refuses_future(store):
    with store.tx() as c:c.execute('PRAGMA user_version=999')
    with pytest.raises(RuntimeError,match='unsupported'):Store(store.path)
    with store.tx() as c:assert c.execute('PRAGMA user_version').fetchone()[0]==999

def test_restore_fences_active_jobs(store,tmp_path):
    a=store.submit('running');j=store.claim(['echo']);b=store.submit('cancel');store.claim(['echo']);store.cancel(b)
    c=store.submit('waiting',approval=True);snapshot=tmp_path/'backup.db';store.backup(snapshot)
    restored=Store.restore(snapshot,tmp_path/'restored.db')
    assert restored.get(a)['state']==restored.get(b)['state']=='uncertain'
    assert restored.get(c)['state']=='waiting_approval'
    assert not restored.finish(a,j['lease_token'],result='old')
    assert restored.events(a)[-1]['kind']=='restored_uncertain'
    assert store.get(a)['state']=='running'
    with pytest.raises(FileExistsError):Store.restore(snapshot,store.path)

def test_restore_rejects_invalid_snapshot(tmp_path):
    snapshot=tmp_path/'unrelated.db';target=tmp_path/'target.db'
    with sqlite3.connect(snapshot) as c:c.execute('CREATE TABLE unrelated (id INTEGER)')
    with pytest.raises(ValueError):Store.restore(snapshot,target)
    assert not target.exists()

@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux subreaper fixture; macOS has best-effort process groups')
@pytest.mark.parametrize('mode',['cancel','timeout','leader_exit'])
def test_process_group_cleanup(tmp_path,monkeypatch,mode):
    exe=tmp_path/'codex';ready=tmp_path/'ready';sentinel=tmp_path/'escaped'
    child=f'import time; from pathlib import Path; Path({str(ready)!r}).touch(); time.sleep(4); Path({str(sentinel)!r}).touch()'
    exe.write_text('#!'+sys.executable+'\n'+f'import subprocess,sys,time\nfrom pathlib import Path\nsubprocess.Popen([sys.executable,"-c",{child!r}])\nwhile not Path({str(ready)!r}).exists(): time.sleep(.01)\n'+('Path(sys.argv[5]).write_text("done")\n' if mode=='leader_exit' else 'time.sleep(20)\n'))
    exe.chmod(0o700);monkeypatch.setenv('PATH',str(tmp_path));adapter=codex_adapter(tmp_path)
    interrupt=threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        f=pool.submit(adapter,'work',3 if mode=='timeout' else 8,cancel_event=interrupt)
        until=time.monotonic()+5
        while not ready.exists() and time.monotonic()<until:time.sleep(.01)
        assert ready.exists()
        if mode=='cancel':
            interrupt.set()
            with pytest.raises(ExecutionStopped):f.result(5)
        elif mode=='timeout':
            with pytest.raises(__import__('subprocess').TimeoutExpired):f.result(5)
        else:assert f.result(5)=='done'
    time.sleep(4.1);assert not sentinel.exists()
