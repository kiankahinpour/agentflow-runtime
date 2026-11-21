import os, sys, time, threading, subprocess
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from agentflow_runtime import Store, Worker, Conflict, ExecutionStopped
from agentflow_runtime.plugins import AdapterSpec, Registry, default_registry
from agentflow_runtime.api import create_app
from agentflow_runtime.adapters import codex_adapter, _launch, _stop_tree

TOKEN='standalone-local-token-123456789'
H={'Authorization':'Bearer '+TOKEN}

def test_restore_holds_pending_and_retries(tmp_path):
    original=Store(tmp_path/'old.db');a=original.submit('old echo');b=original.submit('old plugin','word-count')
    snapshot=original.backup(tmp_path/'snapshot.db');restored=Store.restore(snapshot,tmp_path/'new.db')
    assert restored.claim(['echo','word-count']) is None
    assert restored.get(a)['state']==restored.get(b)['state']=='restored_hold'
    with pytest.raises(Conflict): restored.approve(a)
    assert restored.resolve(a,'retry','verified absent external effects')=='queued'
    assert restored.resolve(b,'retry','reviewed old snapshot')=='waiting_approval'
    assert restored.events(a)[-2]['kind']=='restored_hold'
    assert original.get(a)['state']=='queued'
    assert Worker(restored,default_registry().mapping()).once()
    assert restored.get(a)['state']=='succeeded'

def test_restore_old_queue_can_be_cancelled(tmp_path):
    s=Store(tmp_path/'s.db');j=s.submit('old');r=Store.restore(s.backup(tmp_path/'b.db'),tmp_path/'r.db')
    assert r.cancel(j)=='cancelled';assert r.claim(['echo']) is None

def test_registry_validation():
    spec=AdapterSpec('custom',lambda p,t:p);r=Registry().register(spec)
    with pytest.raises(ValueError):r.register(spec)
    with pytest.raises(ValueError):AdapterSpec('bad/name',lambda p,t:p)
    with pytest.raises(ValueError):AdapterSpec('custom',lambda p,t:p,protocol_version=999)
    with pytest.raises(ValueError):r.load('invalid')
    with pytest.raises(ValueError):r.load('nonexistent_agentflow_plugin:PLUGIN')

def test_explicit_import_and_execute(tmp_path,monkeypatch):
    (tmp_path/'local_plugin.py').write_text("from agentflow_runtime.plugins import AdapterSpec\nPLUGIN=AdapterSpec('upper',lambda p,t:p.upper())\n")
    monkeypatch.syspath_prepend(str(tmp_path));r=default_registry().load('local_plugin:PLUGIN')
    s=Store(tmp_path/'s.db');client=TestClient(create_app(s,TOKEN,r))
    assert client.get('/api/adapters').status_code==401
    assert 'upper' in [a['name'] for a in client.get('/api/adapters',headers=H).json()]
    j=client.post('/api/jobs',headers=H,json={'adapter':'upper','prompt':'hi'}).json()['id'];assert s.claim(['upper']) is None
    s.approve(j);assert Worker(s,r.mapping()).once();assert s.get(j)['result']=='HI'

def test_external_adapter_no_automatic_retry(tmp_path):
    s=Store(tmp_path/'s.db');j=s.submit('external','custom',max_attempts=3);job=s.claim(['custom'])
    assert s.finish(j,job['lease_token'],error='unknown side effects');assert s.get(j)['state']=='uncertain'
    assert s.claim(['custom']) is None
    assert s.resolve(j,'retry','verified safe')=='waiting_approval'

def test_offline_word_count(tmp_path):
    s=Store(tmp_path/'s.db');j=s.submit('one two three','word-count');assert Worker(s,default_registry().mapping()).once();assert s.get(j)['result']=='3'

@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux subreaper')
@pytest.mark.parametrize('mode',['cancel','timeout','leader_exit'])
def test_detached_child_cleanup(tmp_path,monkeypatch,mode):
    exe=tmp_path/'codex';ready=tmp_path/'ready';sentinel=tmp_path/'escaped'
    child=f'import time,os; from pathlib import Path; os.setsid(); Path({str(ready)!r}).touch(); time.sleep(3); Path({str(sentinel)!r}).touch()'
    exe.write_text('#!'+sys.executable+'\n'+f'import subprocess,sys,time\nfrom pathlib import Path\nsubprocess.Popen([sys.executable,"-c",{child!r}])\nwhile not Path({str(ready)!r}).exists(): time.sleep(.01)\n'+('Path(sys.argv[5]).write_text("done")\n' if mode=='leader_exit' else 'time.sleep(20)\n'))
    exe.chmod(0o700);monkeypatch.setenv('PATH',str(tmp_path));adapter=codex_adapter(tmp_path);interrupt=threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        f=pool.submit(adapter,'work',2 if mode=='timeout' else 8,cancel_event=interrupt)
        until=time.monotonic()+6
        while not ready.exists() and time.monotonic()<until:time.sleep(.01)
        assert ready.exists()
        if mode=='cancel':
            interrupt.set()
            with pytest.raises(ExecutionStopped):f.result(8)
        elif mode=='timeout':
            with pytest.raises(subprocess.TimeoutExpired):f.result(8)
        else:assert f.result(8)=='done'
    time.sleep(3.1);assert not sentinel.exists()

@pytest.mark.skipif(os.name!='nt',reason='native Windows Job Object test')
def test_windows_job_cleans_child(tmp_path):
    ready=tmp_path/'ready';sentinel=tmp_path/'escaped';inp=tmp_path/'input';inp.write_text('')
    child=f'import time;from pathlib import Path;Path({str(ready)!r}).touch();time.sleep(4);Path({str(sentinel)!r}).touch()'
    parent=f'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",{child!r}]);time.sleep(30)'
    with inp.open('rb') as f:
        proc,job=_launch([sys.executable,'-c',parent],tmp_path,f,tmp_path)
        try:
            end=time.monotonic()+8
            while not ready.exists() and time.monotonic()<end:time.sleep(.02)
            assert ready.exists();assert _stop_tree(proc,job)
        finally:job.close()
    time.sleep(4.1);assert not sentinel.exists()

@pytest.mark.parametrize('status,payload,expected',[(200,{'done':True,'response':'local result'},'local result'),(200,{'done':False,'response':'partial'},None),(500,{},None)])
def test_ollama_wire_contract(monkeypatch,status,payload,expected):
    import json
    from agentflow_runtime.ollama import ollama_adapter
    class Response:
        def read(self,limit):return json.dumps(payload).encode()
    class Connection:
        def __init__(self,host,port,timeout):assert (host,port,timeout)==('127.0.0.1',11434,7)
        def request(self,method,path,body,headers):
            assert (method,path)==('POST','/api/generate');assert json.loads(body)=={'model':'local-model','prompt':'hello','stream':False}
        def getresponse(self):r=Response();r.status=status;return r
        def close(self):pass
    monkeypatch.setattr('agentflow_runtime.ollama.http.client.HTTPConnection',Connection)
    adapter=ollama_adapter('local-model')
    if expected is None:
        with pytest.raises(RuntimeError):adapter('hello',7)
    else:assert adapter('hello',7)==expected
