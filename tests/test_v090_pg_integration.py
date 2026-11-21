"""Live integration: requires an explicitly disposable PostgreSQL database."""
import os
import uuid
import pytest

@pytest.mark.skipif(not os.getenv('AGENTFLOW_TEST_POSTGRES_DSN'), reason='requires disposable PostgreSQL')
def test_postgres_v090_rate_limit_audit_and_pool():
    from agentflow_runtime.postgres import PostgresStore
    dsn=os.environ['AGENTFLOW_TEST_POSTGRES_DSN']
    store=PostgresStore(dsn,pool_size=3)
    try:
        actor='test-'+uuid.uuid4().hex
        assert store.rate_limit(actor,2,now=120)[0]
        assert store.rate_limit(actor,2,now=120)[0]
        assert not store.rate_limit(actor,2,now=120)[0]
        store.audit(actor,'test','test-resource')
        assert any(r['actor']==actor for r in store.audit_records())
        conn=store.connect()
        assert conn.raw is not None
        conn.close()
    finally:
        store.close()
