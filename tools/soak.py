"""Multi-process local synthetic soak: continuous bounded production, no API calls."""
import argparse,json,multiprocessing as mp,time,tempfile,sqlite3,platform
from contextlib import closing
from pathlib import Path
from agentflow_runtime import Store,Worker
from agentflow_runtime.adapters import echo

def consume(path,stop):
    s=Store(path);w=Worker(s,{'echo':echo})
    while not stop.is_set():
        if not w.once():time.sleep(.02)

def run(seconds,workers,rate):
    ctx=mp.get_context('spawn')
    with tempfile.TemporaryDirectory() as d:
        path=str(Path(d)/'soak.db');s=Store(path);stop=ctx.Event();ps=[ctx.Process(target=consume,args=(path,stop)) for _ in range(workers)]
        count=0;start=time.monotonic()
        try:
            for p in ps:p.start()
            while time.monotonic()-start<seconds:
                for _ in range(rate):s.submit(f'echo-{count}',idem=f'key-{count}');count+=1
                target=start+count/rate;time.sleep(max(0,min(1,target-time.monotonic())))
            until=time.monotonic()+30
            while s.statistics()['states'].get('succeeded',0)!=count and time.monotonic()<until:time.sleep(.1)
        finally:
            stop.set()
            for p in ps:
                if p.pid is not None:p.join(10)
                if p.is_alive():p.terminate();p.join()
        elapsed=time.monotonic()-start
        with closing(sqlite3.connect(path)) as c:
            duplicate=c.execute("SELECT count(*) FROM (SELECT job_id FROM events WHERE kind='claimed' GROUP BY job_id HAVING count(*)!=1)").fetchone()[0]
            claims=c.execute("SELECT count(*) FROM events WHERE kind='claimed'").fetchone()[0]
            integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
        states=s.statistics()['states'];assert states=={'succeeded':count} and duplicate==0 and claims==count and integrity=='ok' and all(p.exitcode==0 for p in ps)
        return dict(jobs=count,workers=workers,production_seconds=seconds,wall_seconds=round(elapsed,3),states=states,duplicate_claims=duplicate,claims=claims,integrity=integrity,exit_codes=[p.exitcode for p in ps],platform=platform.system(),python=platform.python_version(),workload='paced synthetic echo, independent OS processes')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=60);p.add_argument('--workers',type=int,default=4);p.add_argument('--rate',type=int,default=100);a=p.parse_args()
    if not 1<=a.seconds<=86400 or not 1<=a.workers<=16 or not 1<=a.rate<=1000:p.error('invalid bounds')
    print(json.dumps(run(a.seconds,a.workers,a.rate),indent=2))
