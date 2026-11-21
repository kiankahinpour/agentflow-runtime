"""Force-kill a local worker: expired lease MUST become uncertain, never replay.

Run: python tools/fault_worker_smoke.py --json path.json
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from agentflow_runtime import Store

CHILD=r"""
import sys,time
from pathlib import Path
from agentflow_runtime import Store,Worker
path,marker=sys.argv[1:]
def slow(prompt,timeout):
    Path(marker).write_text('started')
    time.sleep(30)
    return 'should never finish'
Worker(Store(path),{'echo':slow},lease=.8).once()
"""

def run():
    with tempfile.TemporaryDirectory() as folder:
        db=Path(folder)/'queue.db'; marker=Path(folder)/'started';store=Store(db)
        job=store.submit('test-forced-kill',idem='fault-smoke')
        env=os.environ.copy()
        env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
        proc=subprocess.Popen([sys.executable,'-c',CHILD,str(db),str(marker)],env=env)
        try:
            deadline=time.monotonic()+15
            while not marker.exists() and time.monotonic()<deadline:
                if proc.poll() is not None:raise RuntimeError('worker ended before reaching workload')
                time.sleep(.03)
            if not marker.exists():raise RuntimeError('worker did not start')
            assert store.get(job)['state']=='running'
            proc.kill();proc.wait(timeout=5)
            time.sleep(1.05)
            changed=store.recover_expired()
            value=store.get(job)
            assert changed==1 and value['state']=='uncertain' and value['attempts']==1
            assert store.claim(['echo'],.8) is None
            return {'status':'passed','injected':'TerminateProcess' if os.name=='nt' else 'SIGKILL',
                    'pid':proc.pid,'exit_code':proc.returncode,'job_state':value['state'],
                    'attempts':value['attempts'],'automatic_replay':False}
        finally:
            if proc.poll() is None:proc.kill();proc.wait(timeout=5)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--json');a=parser.parse_args()
    result=run()
    if a.json:Path(a.json).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
