"""Manual network fault injection for disposable Docker-hosted PostgreSQL.

Requires --allow-disruption and explicit container + network. Disconnects PG
container from test network, checks a supplied health command fails, then
reconnects in finally. DO NOT use against production or shared networks.
"""
import argparse
import re
import subprocess
import time
import os

SAFE=re.compile(r'[a-zA-Z0-9_.-]{1,96}\Z')
def execute(args,timeout=25):
    return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)

def _probe(dsn):
    import psycopg
    try:
        with psycopg.connect(dsn,connect_timeout=2) as connection:
            connection.execute('SELECT 1').fetchone()
        return True
    except psycopg.OperationalError:
        return False

def run(container,network,dsn):
    if not SAFE.fullmatch(container) or not SAFE.fullmatch(network):raise ValueError('unsafe Docker resource name')
    inspect=execute(['docker','inspect','--format','{{json .NetworkSettings.Networks}}',container])
    if inspect.returncode:raise RuntimeError('container is unavailable')
    if ('"'+network+'"').encode() not in inspect.stdout:raise ValueError('container not attached to named network')
    if not _probe(dsn):raise RuntimeError('PostgreSQL is not reachable before injection')
    detached=False
    observed_failure=False
    try:
        result=execute(['docker','network','disconnect','-f',network,container]);
        if result.returncode:raise RuntimeError('network disconnect failed')
        detached=True
        time.sleep(1)
        observed_failure=not _probe(dsn)
        if not observed_failure:raise RuntimeError('database connectivity did not fail: injection ineffective')
    finally:
        if detached:
            connected=execute(['docker','network','connect',network,container])
            if connected.returncode:raise RuntimeError('CRITICAL: network reconnect failed; restore manually')
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if _probe(dsn):break
                time.sleep(1)
            else:raise RuntimeError('PostgreSQL did not recover after network reconnect')
    return {'status':'passed','partition_observed':observed_failure,'recovered':True} 

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--container',required=True);p.add_argument('--network',required=True)
    p.add_argument('--dsn-env',default='AGENTFLOW_TEST_POSTGRES_DSN');p.add_argument('--allow-disruption',action='store_true');a=p.parse_args()
    if not a.allow_disruption:p.error('pass --allow-disruption only for a disposable test deployment')
    dsn=os.environ.get(a.dsn_env)
    if not dsn: p.error('test PostgreSQL DSN environment variable required')
    print(run(a.container,a.network,dsn))
