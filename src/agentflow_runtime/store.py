"""SQLite state machine. All state changes and audit events are atomic."""
import sqlite3
import hashlib
import hmac
import os
import math
import time
import uuid
import json
from contextlib import contextmanager, closing
from pathlib import Path

class Conflict(Exception):
    pass

SCHEMA_VERSION = 6  # SQLite schema; PostgreSQL has its own versioned schema.

def audit_signing_key():
    value=os.environ.get('AGENTFLOW_AUDIT_HMAC_KEY')
    if value is None:return None
    if len(value.encode('utf-8'))<32:raise ValueError('AGENTFLOW_AUDIT_HMAC_KEY must be at least 32 UTF-8 bytes')
    return value.encode('utf-8')

def _audit_digest(key, previous, record):
    data={name:record[name] for name in ('seq','at','actor','action','resource','outcome')}
    payload=previous+'|'+json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    return hmac.new(key,payload.encode('utf-8'),hashlib.sha256).hexdigest()

class Store:
    def __init__(self, path):
        self._audit_key = audit_signing_key()
        self.path = str(Path(path).expanduser().resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.tx() as c:
            version=c.execute('PRAGMA user_version').fetchone()[0]
            if version>SCHEMA_VERSION: raise RuntimeError(f'unsupported database schema {version}')
            # Execute individually: executescript would implicitly commit the migration.
            ddl='''
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, idem TEXT UNIQUE, adapter TEXT NOT NULL,
              prompt TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
              max_attempts INTEGER NOT NULL, available REAL NOT NULL, lease_until REAL,
              lease_token TEXT, created REAL NOT NULL, updated REAL NOT NULL,
              result TEXT, error TEXT, timeout INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS ready ON jobs(state,available,created);
            CREATE TABLE IF NOT EXISTS events (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
              at REAL NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS job_events ON events(job_id,seq);
            CREATE INDEX IF NOT EXISTS active_leases ON jobs(state,lease_until);
            CREATE TABLE IF NOT EXISTS workers (
              id TEXT PRIMARY KEY, pid INTEGER NOT NULL, adapters TEXT NOT NULL,
              status TEXT NOT NULL, job_id TEXT, seen REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS worker_seen ON workers(seen);
            CREATE TABLE IF NOT EXISTS workflows (
              id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL, spec TEXT NOT NULL,
              state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS workflow_steps (
              workflow_id TEXT NOT NULL, name TEXT NOT NULL, job_id TEXT UNIQUE,
              PRIMARY KEY(workflow_id,name));
            CREATE TABLE IF NOT EXISTS github_deliveries (
              digest TEXT PRIMARY KEY, delivery_id TEXT UNIQUE NOT NULL, workflow_id TEXT NOT NULL, created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS workflows_state ON workflows(state,created);
            CREATE TABLE IF NOT EXISTS api_rate_limits (actor TEXT NOT NULL, bucket INTEGER NOT NULL, count INTEGER NOT NULL, PRIMARY KEY(actor,bucket));
            CREATE TABLE IF NOT EXISTS audit_records (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, resource TEXT NOT NULL, outcome TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS audit_at ON audit_records(at);
            CREATE TABLE IF NOT EXISTS audit_integrity (seq INTEGER PRIMARY KEY, previous_mac TEXT NOT NULL, mac TEXT NOT NULL);
            '''
            for statement in ddl.split(';'):
                if statement.strip(): c.execute(statement)
            c.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        with closing(self.connect()) as c:
            c.execute('PRAGMA journal_mode=WAL')

    def connect(self):
        c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA busy_timeout=10000')
        return c

    @contextmanager
    def tx(self):
        c = self.connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    @staticmethod
    def event(c, job, kind, detail=''):
        c.execute('INSERT INTO events(job_id,at,kind,detail) VALUES(?,?,?,?)',
                  (job, time.time(), kind, detail[:4000]))

    def submit(self, prompt, adapter='echo', *, idem=None, max_attempts=1,
               approval=False, timeout=300):
        if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>100_000:
            raise ValueError('prompt must contain 1–100000 characters')
        if not isinstance(adapter,str) or not adapter or len(adapter)>64:
            raise ValueError('invalid adapter')
        if idem is not None and (not isinstance(idem,str) or not idem or len(idem)>256):
            raise ValueError('invalid idempotency key')
        if type(max_attempts) is not int or not 1<=max_attempts<=10 or type(timeout) is not int or not 1<=timeout<=3600:
            raise ValueError('max_attempts 1–10; timeout 1–3600 seconds')
        with self.tx() as c:
            if idem is not None:
                old=c.execute('SELECT * FROM jobs WHERE idem=?',(idem,)).fetchone()
                if old:
                    # Approval is part of the original request, not mutable job state.
                    initial=c.execute('SELECT detail FROM events WHERE job_id=? AND kind=? ORDER BY seq LIMIT 1',(old['id'],'submitted')).fetchone()
                    if (old['prompt'],old['adapter'],old['max_attempts'],old['timeout'],initial['detail']) != (prompt,adapter,max_attempts,timeout,str(bool(approval))):
                        raise Conflict('idempotency key already used with different parameters')
                    return old['id']
            ident=uuid.uuid4().hex; now=time.time()
            c.execute('INSERT INTO jobs(id,idem,adapter,prompt,state,max_attempts,available,created,updated,timeout) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (ident,idem,adapter,prompt,'waiting_approval' if approval else 'queued',max_attempts,now,now,now,timeout))
            self.event(c,ident,'submitted',str(bool(approval)))
            return ident

    def approve(self, ident):
        with self.tx() as c:
            cur=c.execute("UPDATE jobs SET state='queued',available=?,updated=? WHERE id=? AND state='waiting_approval'",(time.time(),time.time(),ident))
            if not cur.rowcount: raise Conflict('job is not awaiting approval')
            self.event(c,ident,'approved')

    def cancel(self, ident):
        """Request cancellation; running work is not declared stopped prematurely."""
        with self.tx() as c:
            now=time.time()
            self._recover(c,now)
            row=c.execute('SELECT state FROM jobs WHERE id=?',(ident,)).fetchone()
            if row is None: raise Conflict('job not found')
            if row['state']=='cancel_requested': return 'cancel_requested'
            if row['state'] not in ('queued','waiting_approval','restored_hold','running'):
                raise Conflict('job cannot be cancelled in its current state')
            state='cancel_requested' if row['state']=='running' else 'cancelled'
            c.execute('UPDATE jobs SET state=?,updated=? WHERE id=?',(state,now,ident))
            self.event(c,ident,state)
            return state

    def _recover(self, c, now):
        # External side effects may already have happened. Never silently replay.
        expired = c.execute("SELECT id FROM jobs WHERE state IN ('running','cancel_requested') AND lease_until<=?", (now,)).fetchall()
        for row in expired:
            c.execute("UPDATE jobs SET state='uncertain',lease_token=NULL,lease_until=NULL,updated=?,error='worker lease expired; inspect external effects' WHERE id=?", (now,row['id']))
            self.event(c,row['id'],'lease_expired')
        return len(expired)

    def recover_expired(self):
        with self.tx() as c:
            return self._recover(c, time.time())

    def resolve(self, ident, decision, reason):
        """Operator has independently verified external effects before resolving."""
        if decision not in ('retry','failed','succeeded','cancelled'):
            raise ValueError('invalid resolution')
        if not isinstance(reason,str) or not reason.strip() or len(reason)>1000:
            raise ValueError('resolution reason must contain 1–1000 characters')
        with self.tx() as c:
            now=time.time()
            row=c.execute("SELECT * FROM jobs WHERE id=? AND state IN ('uncertain','restored_hold')",(ident,)).fetchone()
            if row is None: raise Conflict('only uncertain or restored-held jobs can be resolved')
            if decision=='retry' and row['attempts']>=row['max_attempts']:
                raise Conflict('retry budget exhausted; submit a new task if appropriate')
            # A Codex replay must pass through explicit approval again.
            state=('waiting_approval' if row['adapter']!='echo' else 'queued') if decision=='retry' else decision
            c.execute('UPDATE jobs SET state=?,available=?,updated=?,error=? WHERE id=?',
                      (state,now,now,reason if state in ('failed','cancelled') else None,ident))
            self.event(c,ident,'resolved_'+decision,reason)
            return state

    def rate_limit(self, actor, max_requests=120, *, now=None):
        """Atomic fixed-minute cap shared by worker processes using the same store."""
        if not isinstance(actor,str) or len(actor)>96 or not actor:raise ValueError('invalid actor')
        if type(max_requests) is not int or not 1<=max_requests<=100000:raise ValueError('invalid rate limit')
        now=time.time() if now is None else now
        bucket=int(now//60)
        with self.tx() as c:
            c.execute('DELETE FROM api_rate_limits WHERE bucket<?',(bucket-2,))
            c.execute('INSERT INTO api_rate_limits(actor,bucket,count) VALUES(?,?,1) ON CONFLICT(actor,bucket) DO UPDATE SET count=api_rate_limits.count+1',(actor,bucket))
            n=c.execute('SELECT count FROM api_rate_limits WHERE actor=? AND bucket=?',(actor,bucket)).fetchone()['count']
        return n<=max_requests, max(1,60-int(now%60))

    def audit(self, actor, action, resource, outcome='ok'):
        """Append operator action; optionally sign with an external HMAC key.

        Historical unsigned rows are never represented as authenticated.
        Every signed append is in the same SQL transaction as its audit record.
        """
        fields=(actor,action,resource,outcome)
        if any(not isinstance(v,str) or not v or len(v)>256 for v in fields):raise ValueError('invalid audit fields')
        with self.tx() as c:
            at=time.time()
            inserted=c.execute('INSERT INTO audit_records(at,actor,action,resource,outcome) VALUES(?,?,?,?,?) RETURNING seq,at,actor,action,resource,outcome',(at,*fields)).fetchone()
            if self._audit_key:
                last=c.execute('SELECT mac FROM audit_integrity ORDER BY seq DESC LIMIT 1').fetchone()
                previous=last['mac'] if last else '0'*64
                digest=_audit_digest(self._audit_key, previous, inserted)
                c.execute('INSERT INTO audit_integrity(seq,previous_mac,mac) VALUES(?,?,?)',(inserted['seq'],previous,digest))

    def audit_verify(self, expected_tip=None):
        """Detect modified signed rows or chain breaks; not historical unsigned rows.

        An external expected tip detects deletion of the last signed records.
        """
        if expected_tip is not None and (not isinstance(expected_tip,str) or len(expected_tip)!=64 or any(x not in '0123456789abcdef' for x in expected_tip)):
            raise ValueError('expected tip must be a SHA256 hex digest')
        with closing(self.connect()) as c:
            records=[dict(x) for x in c.execute('SELECT seq,at,actor,action,resource,outcome FROM audit_records ORDER BY seq')]
            signatures={x['seq']:dict(x) for x in c.execute('SELECT seq,previous_mac,mac FROM audit_integrity ORDER BY seq')}
        if not self._audit_key:
            return {'verified':False,'reason':'audit signing key not configured','signed':len(signatures),'unsigned':len(records),'tip':None}
        previous='0'*64;first=min(signatures) if signatures else None; unsigned=0
        for record in records:
            seq=record['seq']; signature=signatures.get(seq)
            if signature is None:
                unsigned+=1
                if first is not None and seq>first:
                    return {'verified':False,'reason':'unsigned row after signed records','seq':seq}
                continue
            if not hmac.compare_digest(signature['previous_mac'],previous) or not hmac.compare_digest(signature['mac'],_audit_digest(self._audit_key,previous,record)):
                return {'verified':False,'reason':'signed row modified or chain broken','seq':seq}
            previous=signature['mac']
        if len(signatures)!=len(records)-unsigned:
            return {'verified':False,'reason':'signature without audit row'}
        if expected_tip is not None and not hmac.compare_digest(previous,expected_tip):
            return {'verified':False,'reason':'expected external checkpoint does not match'}
        return {'verified':True,'signed':len(signatures),'unsigned_legacy':unsigned,'tip':previous if signatures else None,'expected_tip_matched':expected_tip is not None}

    def audit_records(self,limit=100):
        with closing(self.connect()) as c:
            return [dict(r) for r in c.execute('SELECT seq,at,actor,action,resource,outcome FROM audit_records ORDER BY seq DESC LIMIT ?',(max(1,min(limit,500)),))]

    def statistics(self):
        with closing(self.connect()) as c:
            counts={r['state']:r['n'] for r in c.execute('SELECT state,count(*) AS n FROM jobs GROUP BY state')}
            return {'total':sum(counts.values()),'states':counts}

    def backup(self, destination):
        """Consistent SQLite snapshot, including WAL; never overwrite a file."""
        target=Path(destination).expanduser().resolve()
        fd=os.open(target, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        os.close(fd)
        try:
            with closing(self.connect()) as src, closing(sqlite3.connect(target)) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                    raise RuntimeError('backup integrity check failed')
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return str(target)

    @classmethod
    def restore(cls, snapshot, destination):
        """Restore to a new offline database; fence all in-flight snapshot jobs."""
        source=Path(snapshot).expanduser().resolve(strict=True)
        target=Path(destination).expanduser().resolve()
        if not source.is_file(): raise ValueError('snapshot must be a file')
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        os.close(fd)
        try:
            with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src, closing(sqlite3.connect(target)) as dst:
                if src.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise ValueError('invalid snapshot')
                if src.execute('PRAGMA user_version').fetchone()[0]>SCHEMA_VERSION: raise ValueError('snapshot schema is newer than runtime')
                for table, required in [('jobs',{'id','state','lease_token','lease_until','prompt','adapter','attempts','max_attempts','available','created','updated','result','error','timeout','idem'}),('events',{'seq','job_id','at','kind','detail'})]:
                    if not required <= {r[1] for r in src.execute(f'PRAGMA table_info({table})')}: raise ValueError('not an AgentFlow snapshot')
                src.backup(dst)
            restored=cls(target)
            with restored.tx() as c:
                c.execute("DELETE FROM workers")
                c.execute("UPDATE workflows SET state='held',updated=? WHERE state='active'",(time.time(),))
                rows=c.execute("SELECT id FROM jobs WHERE state IN ('running','cancel_requested')").fetchall()
                for row in rows:
                    c.execute("UPDATE jobs SET state='uncertain',lease_token=NULL,lease_until=NULL,updated=?,error='restored in-flight snapshot; inspect external effects' WHERE id=?",(time.time(),row['id']))
                    restored.event(c,row['id'],'restored_uncertain')
                for row in c.execute("SELECT id FROM jobs WHERE state='queued'").fetchall():
                    c.execute("UPDATE jobs SET state='restored_hold',updated=?,error='snapshot queue requires review before replay' WHERE id=?",(time.time(),row['id']))
                    restored.event(c,row['id'],'restored_hold')
            return restored
        except BaseException:
            for suffix in ('','-wal','-shm'):
                Path(str(target)+suffix).unlink(missing_ok=True)
            raise

    def claim(self, adapters, lease=30):
        if not adapters: return None
        if not math.isfinite(lease) or lease<=0: raise ValueError('lease must be positive')
        with self.tx() as c:
            now=time.time()
            self._recover(c, now)
            marks=','.join('?' for _ in adapters)
            row=c.execute(f"SELECT id FROM jobs WHERE state='queued' AND available<=? AND adapter IN ({marks}) ORDER BY available,created LIMIT 1",(now,*adapters)).fetchone()
            if row is None:return None
            ident=row['id']; token=uuid.uuid4().hex
            c.execute("UPDATE jobs SET state='running',attempts=attempts+1,lease_token=?,lease_until=?,updated=? WHERE id=?",(token,now+lease,now,ident))
            self.event(c,ident,'claimed')
            return dict(c.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone())

    def renew(self, ident, token, lease=30):
        """Atomically renew ownership and return current cancellation state."""
        if not math.isfinite(lease) or lease<=0: raise ValueError('lease must be positive')
        with self.tx() as c:
            now=time.time()
            row=c.execute("SELECT state FROM jobs WHERE id=? AND state IN ('running','cancel_requested') AND lease_token=? AND lease_until>?",(ident,token,now)).fetchone()
            if row is None: return None
            c.execute('UPDATE jobs SET lease_until=?,updated=? WHERE id=?',(now+lease,now,ident))
            return row['state']

    def heartbeat(self, ident, token, lease=30):
        return self.renew(ident,token,lease) is not None

    def finish(self, ident, token, *, result=None, error=None, stopped=False):
        with self.tx() as c:
            now=time.time()
            row=c.execute("SELECT * FROM jobs WHERE id=? AND state IN ('running','cancel_requested') AND lease_token=? AND lease_until>?",(ident,token,now)).fetchone()
            if row is None: return False
            # A failed external agent can have partial effects. Require inspection before replay.
            state='succeeded' if error is None else ('uncertain' if row['adapter']!='echo' else ('queued' if row['attempts']<row['max_attempts'] else 'failed'))
            if row['state']=='cancel_requested':
                state='cancelled' if stopped else 'uncertain'
                error='execution stopped; external effects are not rolled back' if stopped else 'cancellation raced with completion or could not be confirmed; inspect external effects'
            elif stopped:
                state='uncertain'; error='execution interrupted; inspect external effects'
            available=now+min(300,2**row['attempts']) if state=='queued' else now
            c.execute('UPDATE jobs SET state=?,available=?,lease_token=NULL,lease_until=NULL,updated=?,result=?,error=? WHERE id=?',
                      (state,available,now,None if error is not None else str(result)[:100000],None if error is None else str(error)[:4000],ident))
            self.event(c,ident,'retry_scheduled' if state=='queued' else state)
            return True

    def get(self, ident):
        with closing(self.connect()) as c:
            row=c.execute('SELECT * FROM jobs WHERE id=?',(ident,)).fetchone()
            return self.public(row) if row else None

    @staticmethod
    def public(row):
        d=dict(row); d.pop('lease_token',None); d.pop('idem',None); return d

    def list(self, limit=50, *, state=None, offset=0):
        if offset<0: raise ValueError('offset must be nonnegative')
        with closing(self.connect()) as c:
            sql='SELECT * FROM jobs'; params=[]
            if state is not None: sql+=' WHERE state=?'; params.append(state)
            sql+=' ORDER BY created DESC,id DESC LIMIT ? OFFSET ?'
            return [self.public(r) for r in c.execute(sql,(*params,max(1,min(limit,200)),offset))]

    def events(self, ident, limit=200, *, after=None):
        with closing(self.connect()) as c:
            limit=max(1,min(limit,500))
            if after is not None:
                return [dict(r) for r in c.execute('SELECT * FROM events WHERE job_id=? AND seq>? ORDER BY seq LIMIT ?',(ident,after,limit))]
            return [dict(r) for r in c.execute('SELECT * FROM events WHERE job_id=? ORDER BY seq DESC LIMIT ?',(ident,limit))][::-1]

    def global_events(self, limit=100, *, after=None):
        limit=max(1,min(limit,500))
        with closing(self.connect()) as c:
            if after is None:
                return [dict(r) for r in c.execute('SELECT seq,job_id,at,kind FROM events ORDER BY seq DESC LIMIT ?',(limit,))][::-1]
            return [dict(r) for r in c.execute('SELECT seq,job_id,at,kind FROM events WHERE seq>? ORDER BY seq LIMIT ?',(after,limit))]

    def worker_status(self, ident, adapters, status, job_id=None):
        with self.tx() as c:
            now=time.time()
            c.execute('INSERT INTO workers VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,job_id=excluded.job_id,seen=excluded.seen',(ident,os.getpid(),json.dumps(sorted(adapters)),status,job_id,now))
            c.execute('DELETE FROM workers WHERE seen<?',(now-86400,))

    def workers(self):
        with closing(self.connect()) as c:
            now=time.time();rows=[]
            for row in c.execute('SELECT * FROM workers ORDER BY seen DESC LIMIT 200'):
                d=dict(row);d['adapters']=json.loads(d['adapters']);d['online']=d['status']!='stopped' and now-d['seen']<10;rows.append(d)
            return rows
