import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from agentflow_runtime import Store, Conflict, Worker
from agentflow_runtime.adapters import echo

@pytest.fixture
def store(tmp_path):return Store(tmp_path/'jobs.db')

def test_idempotency(store):
    a=store.submit('test',idem='one');assert a==store.submit('test',idem='one')
    with pytest.raises(Conflict):store.submit('changed',idem='one')
    with pytest.raises(Conflict):store.submit('test',idem='one',approval=True)

def test_approval(store):
    a=store.submit('test',approval=True);assert store.claim(['echo']) is None
    store.approve(a);assert Worker(store,{'echo':echo}).once();assert store.get(a)['result']=='test'
    assert [e['kind'] for e in store.events(a)]==['submitted','approved','claimed','succeeded']

def test_only_one_claim(store):
    store.submit('test')
    with ThreadPoolExecutor(max_workers=8) as ex:results=list(ex.map(lambda _:store.claim(['echo']),range(20)))
    assert sum(x is not None for x in results)==1

def test_fencing_and_crash(store):
    a=store.submit('test',max_attempts=2);j=store.claim(['echo'],lease=.01);time.sleep(.03)
    assert not store.finish(a,j['lease_token'],result='late')
    assert store.claim(['echo']) is None;assert store.get(a)['state']=='uncertain'

def test_retry(store):
    a=store.submit('test',max_attempts=2);j=store.claim(['echo']);assert store.finish(a,j['lease_token'],error='oops')
    assert store.get(a)['state']=='queued';assert store.claim(['echo']) is None
    with store.tx() as c:c.execute('UPDATE jobs SET available=0 WHERE id=?',(a,))
    assert Worker(store,{'echo':echo}).once();assert store.get(a)['attempts']==2

def test_cancel_and_adapter_routing(store):
    a=store.submit('test','codex');assert store.claim(['echo']) is None
    store.cancel(a);assert store.get(a)['state']=='cancelled'
    with pytest.raises(Conflict):store.cancel(a)

def test_heartbeat(store):
    """Wait for a real renewal rather than relying on a 300ms scheduler window.

    A heavily loaded Windows runner can delay a renewal thread long enough to
    expire a 0.3s lease, correctly fencing completion but making a timing-only
    heartbeat test flaky. Production expired-lease fencing is unchanged.
    """
    import threading
    observed_renewal = threading.Event()
    real_renew = store.renew

    def monitored_renew(*args, **kwargs):
        state = real_renew(*args, **kwargs)
        if state is not None:
            observed_renewal.set()
        return state

    store.renew = monitored_renew

    def wait_for_heartbeat(prompt, timeout):
        assert observed_renewal.wait(4), 'worker did not renew the lease'
        return prompt

    ident = store.submit('test')
    assert Worker(store, {'echo': wait_for_heartbeat}, lease=5).once()
    assert observed_renewal.is_set()
    assert store.get(ident)['state'] == 'succeeded'

def test_default_no_retry(store):
    a=store.submit('test');j=store.claim(['echo']);store.finish(a,j['lease_token'],error='failure')
    assert store.get(a)['state']=='failed'

def test_restart(store):
    a=store.submit('test');reopened=Store(store.path);assert Worker(reopened,{'echo':echo}).once();assert reopened.get(a)['state']=='succeeded'
