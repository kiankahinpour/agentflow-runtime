"""Optional real PostgreSQL integration suite. CI runs it with a PG service.

Use *only* an expendable, dedicated test DB. Job data are never cleaned from a
production DB; distinct test database is a requirement.
"""
import os
import multiprocessing
import uuid
import pytest

def _pg_worker_process(dsn, queue):
    from agentflow_runtime.postgres import PostgresStore
    from agentflow_runtime.worker import Worker
    worker=Worker(PostgresStore(dsn),{'echo':lambda p,t:p})
    n=0
    while worker.once():n+=1
    queue.put(n)


@pytest.mark.skipif(not os.environ.get('AGENTFLOW_TEST_POSTGRES_DSN'),reason='needs disposable PostgreSQL service')
def test_pg_distributed_workers_and_fenced_lease():
    from agentflow_runtime.postgres import PostgresStore
    from agentflow_runtime.worker import Worker
    dsn=os.environ['AGENTFLOW_TEST_POSTGRES_DSN']
    pg=PostgresStore(dsn)
    prefix='multi-'+uuid.uuid4().hex
    keys=[pg.submit(str(i),idem=f'{prefix}-{i}') for i in range(100)]
    ctx=multiprocessing.get_context('spawn')
    out=ctx.Queue()
    workers=[ctx.Process(target=_pg_worker_process,args=(dsn,out)) for _ in range(4)]
    for t in workers:t.start()
    for t in workers:t.join(timeout=90)
    assert all(not t.is_alive() for t in workers)
    assert all(t.exitcode==0 for t in workers)
    assert sum(out.get(timeout=5) for _ in workers)==100
    assert all(pg.get(k)['state']=='succeeded' and pg.get(k)['attempts']==1 for k in keys)

    kid=pg.submit('fence',idem=prefix+'-fenced')
    owned=pg.claim(['echo'],lease=.5)
    assert owned['id']==kid
    assert not pg.finish(kid,'wrong_token',result='bad')
    assert pg.finish(kid,owned['lease_token'],result='good')
