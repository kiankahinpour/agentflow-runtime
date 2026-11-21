"""Live backend contract: only on a disposable PostgreSQL test database."""
import os
import uuid
import pytest

@pytest.mark.skipif(not os.environ.get('AGENTFLOW_TEST_POSTGRES_DSN'),reason='requires real disposable PostgreSQL')
def test_pg_schema3_hmac_audit_and_workflow(monkeypatch):
    from agentflow_runtime.postgres import PostgresStore
    from agentflow_runtime.workflows import Workflows
    from agentflow_runtime.worker import Worker
    from agentflow_runtime.adapters import echo
    monkeypatch.setenv('AGENTFLOW_AUDIT_HMAC_KEY','disposable-postgres-audit-signing-key-123456789')
    store=PostgresStore(os.environ['AGENTFLOW_TEST_POSTGRES_DSN'],pool_size=2)
    try:
        marker=uuid.uuid4().hex
        store.audit('ci','test',marker)
        assert store.audit_verify()['verified']
        wf=Workflows(store).create([{'name':'echo','prompt':'hello'}],'v100-'+marker)
        assert Workflows(store).tick()>=1
        assert Worker(store,{'echo':echo}).once()
        Workflows(store).tick()
        assert Workflows(store).get(wf)['state']=='succeeded'
    finally:
        store.close()
