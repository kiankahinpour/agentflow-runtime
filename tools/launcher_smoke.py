"""End-to-end loopback API smoke for the portable launcher (offline Echo only)."""
from __future__ import annotations
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener


def smoke():
    http = build_opener(ProxyHandler({}))
    with tempfile.TemporaryDirectory(prefix='agentflow-local-smoke-') as temp:
        home=Path(temp)
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        env={**os.environ,'HOME':str(home),'USERPROFILE':str(home)}
        project=Path(__file__).resolve().parents[1]
        env['PYTHONPATH']=str(project/'src')
        kwargs={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {}
        proc=subprocess.Popen([sys.executable,str(project/'tools'/'start_local.py'),'--port',str(port)],cwd=project,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,**kwargs)
        try:
            deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                try:
                    with http.open(f'http://127.0.0.1:{port}/health/ready',timeout=.3) as response:
                        if response.status==200:break
                except Exception:time.sleep(.1)
            else:raise RuntimeError('launcher readiness not observed')
            path=home/'.agentflow_runtime'/'local-token'
            if not path.exists():raise RuntimeError('launcher token missing')
            token=path.read_text().strip()
            req=Request(f'http://127.0.0.1:{port}/api/jobs',data=json.dumps({'prompt':'portable-smoke','adapter':'echo'}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
            with http.open(req,timeout=5) as response:ident=json.load(response)['id']
            for _ in range(80):
                req=Request(f'http://127.0.0.1:{port}/api/jobs/{ident}',headers={'Authorization':'Bearer '+token})
                with http.open(req,timeout=5) as response:task=json.load(response)
                if task['state']=='succeeded':
                    assert task['result']=='portable-smoke'
                    return {'status':'passed','platform':sys.platform,'http':'direct loopback','task_state':task['state']}
                time.sleep(.1)
            raise RuntimeError('worker did not complete task')
        finally:
            if proc.poll() is None:
                if os.name=='nt':proc.send_signal(signal.CTRL_BREAK_EVENT) if hasattr(signal,'CTRL_BREAK_EVENT') else proc.terminate()
                else:proc.terminate()
            try:proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.communicate(timeout=10)

if __name__=='__main__':print(json.dumps(smoke(),indent=2))
