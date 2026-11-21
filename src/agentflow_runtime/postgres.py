"""Optional PostgreSQL backend using psycopg 3.

Transactions deliberately take a *database-local advisory transaction lock* to
serialize the v0.7 state machine, including DAG scheduler and claim. This is
correct for multiple workers/hosts, but throughput is limited by one writer at
any instant. It is NOT a distributed exactly-once external effects guarantee.
"""
from __future__ import annotations

from contextlib import contextmanager
from .store import Store, audit_signing_key

LOCK_KEY = 50705822183644
PG_SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS agentflow_schema (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, idem TEXT UNIQUE, adapter TEXT NOT NULL,
 prompt TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 max_attempts INTEGER NOT NULL, available DOUBLE PRECISION NOT NULL,
 lease_until DOUBLE PRECISION, lease_token TEXT,
 created DOUBLE PRECISION NOT NULL, updated DOUBLE PRECISION NOT NULL,
 result TEXT, error TEXT, timeout INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ready ON jobs(state,available,created);
CREATE INDEX IF NOT EXISTS active_leases ON jobs(state,lease_until);
CREATE TABLE IF NOT EXISTS events (
 seq BIGSERIAL PRIMARY KEY, job_id TEXT NOT NULL,
 at DOUBLE PRECISION NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS job_events ON events(job_id,seq);
CREATE TABLE IF NOT EXISTS workers (
 id TEXT PRIMARY KEY, pid INTEGER NOT NULL, adapters TEXT NOT NULL,
 status TEXT NOT NULL, job_id TEXT, seen DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS worker_seen ON workers(seen);
CREATE TABLE IF NOT EXISTS workflows (
 id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL, spec TEXT NOT NULL,
 state TEXT NOT NULL, created DOUBLE PRECISION NOT NULL, updated DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS workflow_steps (
 workflow_id TEXT NOT NULL, name TEXT NOT NULL, job_id TEXT UNIQUE,
 PRIMARY KEY(workflow_id,name));
CREATE TABLE IF NOT EXISTS github_deliveries (
 digest TEXT PRIMARY KEY, delivery_id TEXT UNIQUE NOT NULL,
 workflow_id TEXT NOT NULL, created DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS workflows_state ON workflows(state,created);
CREATE TABLE IF NOT EXISTS api_rate_limits (actor TEXT NOT NULL, bucket INTEGER NOT NULL, count INTEGER NOT NULL, PRIMARY KEY(actor,bucket));
CREATE TABLE IF NOT EXISTS audit_records (seq BIGSERIAL PRIMARY KEY, at DOUBLE PRECISION NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, resource TEXT NOT NULL, outcome TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS audit_at ON audit_records(at);
CREATE TABLE IF NOT EXISTS audit_integrity (seq BIGINT PRIMARY KEY, previous_mac TEXT NOT NULL, mac TEXT NOT NULL);
"""


def _placeholders(query):
    """All state-machine queries are constant SQL with positional placeholders.
    Never translate user-provided SQL. '?' never occurs inside SQL literals.
    """
    return query.replace('?', '%s')


class PGConnection:
    """Adapter for the small sqlite3 Connection API consumed by Store/Workflows."""
    def __init__(self, conn, pool=None):
        self.raw = conn
        self.pool = pool

    def execute(self, statement, params=()):
        return self.raw.execute(_placeholders(statement), params)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        if self.pool is not None:self.pool.putconn(self.raw)
        else:self.raw.close()


class PostgresStore(Store):
    """PostgreSQL backend for the existing Store API, with cross-host locking.

    Requires optional `psycopg[binary]`. Credentials are accepted only from
    caller-provided DSN (typically AGENTFLOW_POSTGRES_DSN environment variable).
    """
    def __init__(self, dsn, *, pool_size=0):
        if not isinstance(dsn, str) or not dsn or not (dsn.startswith('postgresql://') or dsn.startswith('postgres://')):
            raise ValueError('PostgreSQL DSN must start with postgresql:// or postgres://')
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError('PostgreSQL requires: pip install "agentflow-durable[postgres]"') from exc
        self._audit_key = audit_signing_key()
        self._psycopg = psycopg
        self._row_factory = dict_row
        self._dsn = dsn
        if type(pool_size) is not int or not 0 <= pool_size <= 64:
            raise ValueError('pool_size must be an integer between 0 and 64')
        self._pool = None
        if pool_size:
            try:
                from psycopg_pool import ConnectionPool
            except ImportError as exc:
                raise RuntimeError('pooling requires: pip install "agentflow-durable[postgres-pool]"') from exc
            self._pool = ConnectionPool(conninfo=dsn, min_size=1, max_size=pool_size,
                                        kwargs={'row_factory': dict_row, 'connect_timeout': 8},
                                        open=True)
        self.path = '<postgresql: credentials redacted>'
        with self.tx() as c:
            for sql in SCHEMA.split(';'):
                if sql.strip():
                    c.execute(sql)
            rows = c.execute('SELECT version FROM agentflow_schema').fetchall()
            if len(rows) > 1:
                raise RuntimeError('invalid PostgreSQL schema version history')
            if rows and rows[0]['version'] not in (1,2,PG_SCHEMA_VERSION):
                raise RuntimeError('unsupported PostgreSQL schema version')
            if rows and rows[0]['version'] in (1,2):
                c.execute('UPDATE agentflow_schema SET version=?',(PG_SCHEMA_VERSION,))
            if not rows:
                c.execute('INSERT INTO agentflow_schema(version) VALUES(?)', (PG_SCHEMA_VERSION,))

    def connect(self):
        if self._pool is not None:
            return PGConnection(self._pool.getconn(),self._pool)
        conn = self._psycopg.connect(self._dsn, row_factory=self._row_factory, connect_timeout=8)
        return PGConnection(conn)

    def close(self):
        if self._pool is not None:self._pool.close()

    @contextmanager
    def tx(self):
        c = self.connect()
        try:
            # Ensures claim, workflow tick, idempotency and state transitions are
            # serialized across worker processes and networked hosts.
            c.execute('SELECT pg_advisory_xact_lock(?)', (LOCK_KEY,))
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def backup(self, destination):
        raise RuntimeError('PostgreSQL backup is external: use pg_dump with restricted credentials')

    @classmethod
    def restore(cls, snapshot, destination):
        raise RuntimeError('PostgreSQL restore is external: use pg_restore to a new database, then audit held jobs')
