"""Offline bounded multiprocess soak with deliberate worker termination.

Exercise the SQLite durable queue for seconds-to-hours. Does not call LLMs,
execute untrusted prompts or touch production databases. Running jobs killed
mid-execution become 'uncertain' and are NOT silently replayed.
"""
from __future__ import annotations
import argparse
import json
import multiprocessing as mp
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from agentflow_runtime.store import Store
from agentflow_runtime.worker import Worker


def slow_echo(prompt, timeout):
    time.sleep(.4)
    return prompt


def loop_worker(database, stop):
    store=Store(database)
    worker=Worker(store,{'echo':slow_echo},lease=1.2)
    while not stop.is_set():
        if not worker.once():time.sleep(.025)


def run(seconds, workers, rate, kill_every):
    if not (2 <= seconds <= 14400 and 1 <= workers <= 8 and 1 <= rate <= 100 and 1 <= kill_every <= seconds):
        raise ValueError('invalid synthetic workload parameters')
    ctx=mp.get_context('spawn')
    with tempfile.TemporaryDirectory(prefix='agentflow-chaos-') as folder:
        db=str(Path(folder)/'queue.db')
        store=Store(db)
        stop=ctx.Event()
        processes=[]
        def start_worker():
            proc=ctx.Process(target=loop_worker,args=(db,stop))
            proc.start()
            processes.append(proc)
            return proc
        for _ in range(workers):start_worker()
        injected=0;count=0;start=time.monotonic();next_kill=start+kill_every
        try:
            while time.monotonic()-start<seconds:
                for _ in range(rate):
                    store.submit(f'chaos-{count}',idem=f'chaos-{count}')
                    count+=1
                if time.monotonic()>=next_kill:
                    victim=processes.pop(0)
                    victim.kill();victim.join(timeout=5)
                    assert victim.exitcode is not None
                    injected+=1
                    start_worker()
                    next_kill=time.monotonic()+kill_every
                time.sleep(1)
        finally:
            stop.set()
            for proc in processes:
                proc.join(timeout=4)
                if proc.is_alive():proc.kill();proc.join(timeout=5)
        time.sleep(1.35)
        recovered=store.recover_expired()
        # Complete remaining queued work without fault injection; uncertain jobs
        # must remain uncertain for manual reconciliation.
        fast=Worker(store,{'echo':lambda prompt,timeout:prompt})
        while fast.once():pass
        states=store.statistics()['states']
        with closing(sqlite3.connect(db)) as connection:
            duplicate=connection.execute('SELECT count(*) FROM (SELECT job_id FROM events WHERE kind="claimed" GROUP BY job_id HAVING count(*)>1)').fetchone()[0]
            integrity=connection.execute('PRAGMA integrity_check').fetchone()[0]
        if sum(states.values())!=count or set(states)-{'succeeded','uncertain'} or duplicate or integrity!='ok':
            raise RuntimeError('chaos invariant violation: '+json.dumps(states))
        return {'status':'PASSED','duration_seconds':seconds,'submitted':count,
                'sigkill_injections':injected,'recovered_expired':recovered,
                'termination_mechanism':'TerminateProcess' if os.name=='nt' else 'SIGKILL',
                'states':states,'duplicate_claims':duplicate,'sqlite_integrity':integrity,
                'external_effects':'none (synthetic echo only)'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=3600)
    p.add_argument('--workers',type=int,default=4);p.add_argument('--rate',type=int,default=20)
    p.add_argument('--kill-every',type=int,default=30);a=p.parse_args()
    print(json.dumps(run(a.seconds,a.workers,a.rate,a.kill_every),indent=2))
if __name__=='__main__':main()
