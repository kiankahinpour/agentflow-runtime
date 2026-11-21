"""Cross-platform local demo launcher. Does not enable external agents or remote bind."""
from __future__ import annotations
import argparse
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

def check():
    if sys.version_info < (3,10):raise RuntimeError('Python 3.10+ required')
    try:
        import fastapi, uvicorn, agentflow_runtime
    except ImportError as exc:
        raise RuntimeError('install package with: python -m pip install ".[server]"') from exc
    return {'platform':sys.platform,'python':sys.version.split()[0],'mode':'localhost-only','providers':'echo and word-count only'}

def local_token(root):
    token=os.environ.get('AGENTFLOW_TOKEN')
    if token:
        if len(token)<24:raise ValueError('AGENTFLOW_TOKEN must be at least 24 characters')
        return token
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    if root.is_symlink():raise RuntimeError('refusing symlink data directory')
    if os.name=='posix' and root.stat().st_mode & 0o077:raise PermissionError('local data folder must be owner-only (chmod 700)')
    path=root/'local-token'
    if path.is_symlink():raise RuntimeError('refusing symlink token file')
    if path.exists():
        if os.name=='posix' and path.stat().st_mode & 0o077:raise PermissionError('token file must be chmod 600')
        value=path.read_text().strip()
        if len(value)<24:raise ValueError('invalid existing token')
        return value
    value=secrets.token_urlsafe(36)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f:f.write(value+'\n')
    return value

def launch(port=8787,open_browser=False):
    check()
    if not 1024<=port<=65535:raise ValueError('port must be 1024-65535')
    root=Path.home()/'.agentflow_runtime'
    token=local_token(root)
    env={**os.environ,'AGENTFLOW_TOKEN':token,'AGENTFLOW_DB':str(root/'queue.db')}
    env.pop('AGENTFLOW_CONTAINER_BIND',None)
    env.pop('AGENTFLOW_POSTGRES_DSN',None)
    http=build_opener(ProxyHandler({}))
    cmd=[sys.executable,'-m','agentflow_runtime.cli']
    extra={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
    stop_signals = [signal.SIGTERM]
    if os.name == 'nt':
        stop_signals.append(signal.SIGBREAK)
    previous_handlers = {event: signal.getsignal(event) for event in stop_signals}
    def terminate(_signum,_frame):raise KeyboardInterrupt
    server = worker = None
    try:
        for event in stop_signals:
            signal.signal(event, terminate)
        server=subprocess.Popen([*cmd,'serve','--port',str(port)],env=env,**extra)
        print(f'AgentFlow local dashboard: http://127.0.0.1:{port}',flush=True)
        print('API token: '+('supplied by AGENTFLOW_TOKEN' if os.environ.get('AGENTFLOW_TOKEN') else f'stored at {root/"local-token"}'),flush=True)
        for _ in range(40):
            if server.poll() is not None:raise RuntimeError('server exited before readiness')
            try:
                with http.open(f'http://127.0.0.1:{port}/health/ready',timeout=.5) as reply:
                    if reply.status==200:break
            except Exception:time.sleep(.2)
        else:raise RuntimeError('server readiness was not confirmed')
        # Prevent concurrent migrations on an empty SQLite database.
        worker=subprocess.Popen([*cmd,'worker','--workflows'],env=env,**extra)
        if open_browser:
            import webbrowser
            webbrowser.open(f'http://127.0.0.1:{port}')
        while server.poll() is None and worker.poll() is None:time.sleep(.5)
        raise RuntimeError('server or worker exited unexpectedly')
    except KeyboardInterrupt:
        pass
    finally:
        for process in (server,worker):
            if process is not None and process.poll() is None:process.terminate()
        for process in (server,worker):
            if process is None:continue
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        for event, previous in previous_handlers.items():
            signal.signal(event, previous)

def main():
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');p.add_argument('--port',type=int,default=8787);p.add_argument('--browser',action='store_true')
    args=p.parse_args()
    if args.check_only:
        print(check())
    else:
        launch(args.port,args.browser)
if __name__=='__main__':main()
