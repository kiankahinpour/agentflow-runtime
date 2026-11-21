from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from agentflow_runtime import Store, Conflict
from agentflow_runtime.api import create_app

@pytest.fixture
def store(tmp_path):
    return Store(tmp_path/'state.db')

def expire(store, ident):
    with store.tx() as c:
        c.execute('UPDATE jobs SET lease_until=0 WHERE id=?',(ident,))

def test_recovery_without_worker(store):
    ident=store.submit('task',max_attempts=2)
    job=store.claim(['echo']);expire(store,ident)
    with ThreadPoolExecutor(max_workers=5) as ex:
        assert sum(ex.map(lambda _:store.recover_expired(),range(10)))==1
    assert store.get(ident)['state']=='uncertain'
    assert not store.finish(ident,job['lease_token'],result='stale')
    assert store.resolve(ident,'retry','Verified no external effects')=='queued'
    assert store.claim(['echo'])['attempts']==2
    assert [e['kind'] for e in store.events(ident)].count('lease_expired')==1
    assert any(e['detail']=='Verified no external effects' for e in store.events(ident))

def test_codex_replay_requires_approval(store):
    ident=store.submit('task','codex',max_attempts=2)
    store.claim(['codex']);expire(store,ident);store.recover_expired()
    assert store.resolve(ident,'retry','No effects observed')=='waiting_approval'
    assert store.claim(['codex']) is None
    store.approve(ident);assert store.claim(['codex'])['id']==ident

def test_resolution_constraints(store):
    ident=store.submit('task')
    with pytest.raises(Conflict):store.resolve(ident,'failed','reason')
    store.claim(['echo']);expire(store,ident);store.recover_expired()
    with pytest.raises(Conflict):store.resolve(ident,'retry','reason')
    with pytest.raises(ValueError):store.resolve(ident,'failed',' ')
    assert store.resolve(ident,'succeeded','Verified external outcome')=='succeeded'
    assert store.get(ident)['result'] is None
    with pytest.raises(Conflict):store.resolve(ident,'failed','reason')

def test_backup_snapshot_no_overwrite(store,tmp_path):
    ident=store.submit('first')
    path=tmp_path/'backup.db'
    store.backup(path);store.submit('second')
    copied=Store(path)
    assert copied.get(ident)['prompt']=='first'
    assert copied.statistics()['total']==1
    with pytest.raises(FileExistsError):store.backup(path)
    with pytest.raises(FileExistsError):store.backup(store.path)

def test_global_statistics_and_pagination(store):
    for i in range(205):store.submit(str(i),approval=i%2==0)
    assert store.statistics()=={'total':205,'states':{'queued':102,'waiting_approval':103}}
    a=store.list(50,state='queued');b=store.list(50,state='queued',offset=50)
    assert len(a)==len(b)==50
    assert not {j['id'] for j in a}&{j['id'] for j in b}
    ident=a[0]['id'];first=store.events(ident)[0]['seq']
    store.cancel(ident);assert [e['kind'] for e in store.events(ident,after=first)]==['cancelled']

def test_recovery_api_auth_and_audit(store):
    token='token-for-local-testing-1234';h={'Authorization':'Bearer '+token}
    c=TestClient(create_app(store,token))
    ident=store.submit('task');store.claim(['echo']);expire(store,ident)
    assert c.post('/api/recover').status_code==401
    assert c.post('/api/recover',headers=h).json()=={'recovered':1}
    uri='/api/jobs/'+ident+'/resolve'
    assert c.post(uri,headers=h,json={'decision':'failed','reason':' '}).status_code==422
    assert c.post(uri,json={'decision':'failed','reason':'verified'}).status_code==401
    assert c.post(uri,headers=h,json={'decision':'failed','reason':'verified'}).json()['state']=='failed'
    assert c.get('/api/stats',headers=h).json()['states']=={'failed':1}
    assert c.get('/api/jobs?state=uncertain',headers=h).json()==[]
    assert c.get('/api/jobs/'+ident+'/events?after=0&limit=1',headers=h).json()[0]['kind']=='submitted'

def test_invalid_lease(store):
    store.submit('task')
    for lease in (0,-1,float('nan'),float('inf')):
        with pytest.raises(ValueError):store.claim(['echo'],lease)

def test_codex_error_never_auto_replays(store):
    ident=store.submit('task','codex',max_attempts=2)
    job=store.claim(['codex'])
    assert store.finish(ident,job['lease_token'],error='process failed')
    assert store.get(ident)['state']=='uncertain'
    assert store.claim(['codex']) is None
    assert store.resolve(ident,'retry','Verified no external changes')=='waiting_approval'
