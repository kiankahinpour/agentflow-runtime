"""Local synthetic queue benchmark; no API or model calls."""
import argparse, json, platform, statistics, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from agentflow_runtime import Store, Worker
from agentflow_runtime.adapters import echo

def run(jobs, workers):
    with tempfile.TemporaryDirectory() as directory:
        store=Store(Path(directory)/'bench.db')
        start=time.perf_counter();ids=[store.submit(f'job-{i}',idem=f'key-{i}') for i in range(jobs)];submission=time.perf_counter()-start
        def worker():
            w=Worker(store,{'echo':echo});count=0;latencies=[]
            while True:
                t=time.perf_counter()
                if not w.once():break
                latencies.append((time.perf_counter()-t)*1000);count+=1
            return count,latencies
        start=time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool: results=list(pool.map(lambda _:worker(),range(workers)))
        elapsed=time.perf_counter()-start;lat=sorted(x for _,l in results for x in l)
        counts=store.statistics()['states'];assert counts=={'succeeded':jobs};assert sum(n for n,_ in results)==jobs
        for ident in ids:
            events=store.events(ident);assert sum(e['kind']=='claimed' for e in events)==1
        return {'jobs':jobs,'workers':workers,'successful':counts['succeeded'],'submission_seconds':round(submission,3),'execution_seconds':round(elapsed,3),'jobs_per_second':round(jobs/elapsed,1),'worker_once_p50_ms':round(statistics.median(lat),2),'worker_once_p95_ms':round(lat[min(len(lat)-1,int(len(lat)*.95))],2),'python':platform.python_version(),'platform':platform.system(),'workload':'echo, SQLite local disk; no external model'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--jobs',type=int,default=1000);p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    if a.jobs<1 or not 1<=a.workers<=64:p.error('jobs >=1; workers 1–64')
    print(json.dumps(run(a.jobs,a.workers),indent=2))
