import os,sys,time,threading
import pytest
from fastapi.testclient import TestClient
from agentflow_runtime import Store,Worker
from agentflow_runtime.api import create_app
from agentflow_runtime.external import cli_adapter
from agentflow_runtime.adapters import echo
TOKEN='standalone-local-token-123456789'
H={'Authorization':'Bearer '+TOKEN}

def test_event_cursor_and_stream(tmp_path):
    s=Store(tmp_path/'db');s.submit('secret text');Worker(s,{'echo':echo}).once();c=TestClient(create_app(s,TOKEN))
    assert c.get('/api/events').status_code==401
    assert c.get('/api/events/stream').status_code==401
    rows=c.get('/api/events',headers=H).json();assert len(rows)==3 and all('detail' not in r for r in rows)
    assert c.get('/api/events',headers=H,params={'after':rows[0]['seq'],'limit':1}).json()==[rows[1]]
    r=c.get('/api/events/stream?seconds=1',headers=H);assert r.status_code==200 and 'text/event-stream' in r.headers['content-type'] and 'id: '+str(rows[-1]['seq']) in r.text and 'secret text' not in r.text

def test_worker_roster_restore(tmp_path):
    s=Store(tmp_path/'db');s.worker_status('worker1',['echo'],'idle');s.worker_status('worker2',['echo'],'stopped');c=TestClient(create_app(s,TOKEN))
    assert c.get('/api/workers').status_code==401
    workers={w['id']:w for w in c.get('/api/workers',headers=H).json()};assert workers['worker1']['online'] and not workers['worker2']['online']
    with s.tx() as con:con.execute('UPDATE workers SET seen=? WHERE id=?',(time.time()-15,'worker1'))
    assert not next(w for w in s.workers() if w['id']=='worker1')['online']
    assert Store.restore(s.backup(tmp_path/'snapshot'),tmp_path/'new').workers()==[]

def test_external_catalog_approval(tmp_path):
    s=Store(tmp_path/'db');c=TestClient(create_app(s,TOKEN,external_catalog=['claude','opencode']))
    for name in ['claude','opencode']:
        j=c.post('/api/jobs',headers=H,json={'adapter':name,'prompt':'test'}).json()['id'];assert s.get(j)['state']=='waiting_approval';assert s.claim([name]) is None
    with pytest.raises(ValueError):create_app(s,TOKEN,external_catalog=['bad'])

@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='POSIX fake executable')
@pytest.mark.parametrize('name',['claude','opencode'])
def test_cli_contract(tmp_path,monkeypatch,name):
    exe=tmp_path/name
    script='import sys\n'+('assert sys.argv[1:]==["--print","--output-format","text","--permission-mode","plan","--tools",""]\nassert sys.stdin.read()=="hello"\n' if name=='claude' else 'assert sys.argv[1:]==["run","--standalone","hello"]\n')+'print("reply")\n'
    exe.write_text('#!'+sys.executable+'\n'+script);exe.chmod(0o700);monkeypatch.setenv('PATH',str(tmp_path));assert cli_adapter(name,tmp_path)('hello',8)=='reply'
    if name=='opencode':
        with pytest.raises(ValueError):cli_adapter(name,tmp_path)('--auto',8)

@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='POSIX fake executable')
def test_external_cancellation(tmp_path,monkeypatch):
    from agentflow_runtime.worker import ExecutionStopped
    exe=tmp_path/'claude';ready=tmp_path/'ready';exe.write_text('#!'+sys.executable+'\nimport time\nfrom pathlib import Path\nPath('+repr(str(ready))+').touch()\ntime.sleep(30)\n');exe.chmod(0o700);monkeypatch.setenv('PATH',str(tmp_path));event=threading.Event()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor() as pool:
        f=pool.submit(cli_adapter('claude',tmp_path),'test',15,cancel_event=event);deadline=time.monotonic()+8
        while not ready.exists() and time.monotonic()<deadline:time.sleep(.05)
        assert ready.exists();event.set()
        with pytest.raises(ExecutionStopped):f.result(8)

@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux cgroup')
def test_cgroup_requires_real_delegation(tmp_path):
    from agentflow_runtime.containment import LinuxCgroup
    with pytest.raises(ValueError):LinuxCgroup(tmp_path)
    with pytest.raises(ValueError):LinuxCgroup('/sys/fs/cgroup')

@pytest.mark.skipif(not sys.platform.startswith('linux') or not os.environ.get('AGENTFLOW_TEST_CGROUP_ROOT'),reason='requires delegated cgroup v2')
def test_cgroup_supervisor_crash(tmp_path,monkeypatch):
    from agentflow_runtime.adapters import _launch,_stop_tree
    monkeypatch.setenv('AGENTFLOW_CGROUP_ROOT',os.environ['AGENTFLOW_TEST_CGROUP_ROOT']);ready=tmp_path/'ready';escaped=tmp_path/'escaped';inp=tmp_path/'in';inp.touch()
    child=f'import os,time;from pathlib import Path;os.setsid();Path({str(ready)!r}).touch();time.sleep(3);Path({str(escaped)!r}).touch()'
    parent=f'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",{child!r}]);time.sleep(30)'
    with inp.open('rb') as f:
        proc,job=_launch([sys.executable,'-c',parent],tmp_path,f,tmp_path)
        try:
            end=time.monotonic()+8
            while not ready.exists() and time.monotonic()<end:time.sleep(.03)
            assert ready.exists();proc.kill();proc.wait();assert _stop_tree(proc,job)
        finally:job.close()
    time.sleep(3.1);assert not escaped.exists()
