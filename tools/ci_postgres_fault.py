"""Destructive integration lab on an *ephemeral, isolated Docker Compose project*.

Explicit opt-in. Creates, kills and removes test-only database containers and
volumes belonging to its own unique project name; never touches user services.
Tests real Postgres durability and two independent workers after DB recovery.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
NAME=re.compile(r'^agentflowtest-[a-f0-9]{10}$')


def run(*, allow_destruction=False, include_network_partition=False):
    if not allow_destruction:
        raise PermissionError('explicit --allow-disposable-docker-test required')
    import psycopg
    from agentflow_runtime.postgres import PostgresStore
    from agentflow_runtime.worker import Worker
    from agentflow_runtime.adapters import echo

    ident='agentflowtest-'+secrets.token_hex(5)
    assert NAME.fullmatch(ident)
    passwd=secrets.token_urlsafe(25)
    port=55432  # isolated CI runner; override in dedicated CI runner if occupied
    env={**os.environ,'AGENTFLOW_DB_PASSWORD':passwd,
         'AGENTFLOW_TOKEN':secrets.token_urlsafe(32),
         'AGENTFLOW_TEST_PG_PORT':str(port)}
    dsn=f'postgresql://agentflow:{passwd}@127.0.0.1:{port}/agentflow'
    base=['docker','compose','-p',ident,'-f',str(ROOT/'compose.yaml'),
          '-f',str(ROOT/'compose.ci-fault.yaml')]
    report={'project':ident,'status':'FAILED','postgres':'real Docker container',
            'failure_injected':False,'recovered':False,'duplicate_claims':None}

    def call(*args,timeout=180):
        return subprocess.run([*base,*args],env=env,cwd=ROOT,check=True,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)

    def until_up(seconds=90):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            try:
                with psycopg.connect(dsn,connect_timeout=2) as conn:
                    conn.execute('SELECT 1')
                return
            except psycopg.OperationalError:
                time.sleep(1)
        raise RuntimeError('test Postgres never became healthy')

    try:
        call('up','-d','--no-build','postgres')
        until_up()
        store=PostgresStore(dsn)
        job=store.submit('retained-task',idem='retained-task')
        assert store.get(job)['state']=='queued'
        store.close()
        # Simulate *crash* rather than graceful restart. No data should vanish.
        call('kill','postgres')
        report['failure_injected']=True
        try:
            with psycopg.connect(dsn,connect_timeout=2) as conn:
                conn.execute('SELECT 1')
        except psycopg.OperationalError:
            report['outage_observed']=True
        else:
            raise AssertionError('PostgreSQL was still reachable after kill')
        call('up','-d','--no-build','postgres')
        until_up()
        store=PostgresStore(dsn)
        assert store.get(job)['state']=='queued'
        report['recovered']=True
        # Independent Store instances / connections must not claim a job twice.
        if include_network_partition:
            from tools.network_fault_smoke import run as network_fault
            container_id=call('ps','-q','postgres').stdout.decode().strip()
            if not container_id:
                raise RuntimeError('disposable PostgreSQL container ID unavailable')
            result=network_fault(container_id,ident+'_internal',dsn)
            report['network_partition']=result['status']
        store2=PostgresStore(dsn)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures=[executor.submit(Worker(s,{'echo':echo}).once) for s in (store,store2)]
            claimed=[f.result(timeout=15) for f in futures]
        assert sorted(claimed)==[False,True]
        assert store.get(job)['state']=='succeeded'
        with store.tx() as c:
            claims=c.execute("SELECT count(*) AS n FROM events WHERE job_id=? AND kind='claimed'",(job,)).fetchone()['n']
        assert claims==1
        report['duplicate_claims']=0
        report['status']='PASSED'
        store2.close();store.close()
        return report
    finally:
        # Cleanup is mandatory, even on error. Container's isolated volumes only.
        try:
            call('down','-v','--remove-orphans',timeout=120)
        except (subprocess.SubprocessError,OSError) as exc:
            print('CRITICAL: disposable Docker fixture cleanup failed: '+str(exc),file=sys.stderr)
            raise


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--allow-disposable-docker-test',action='store_true')
    p.add_argument('--include-network-partition',action='store_true')
    a=p.parse_args()
    print(json.dumps(run(allow_destruction=a.allow_disposable_docker_test,include_network_partition=a.include_network_partition),indent=2))

if __name__=='__main__':main()
