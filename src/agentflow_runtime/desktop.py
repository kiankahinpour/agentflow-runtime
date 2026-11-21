"""Portable local-only entry point for source and frozen desktop distributions.

This is a browser-based local UI, not a native GUI toolkit. It intentionally
never accepts external agent, GitHub or tenant configurations.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import socket
import tempfile
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener
from ._version import __version__


def data_dir() -> Path:
    if sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local'))
        return root / 'AgentFlowRuntime'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'AgentFlowRuntime'
    root = Path(os.environ.get('XDG_STATE_HOME') or (Path.home() / '.local' / 'state'))
    return root / 'agentflow-runtime'


def local_token(root: Path) -> str:
    configured = os.environ.get('AGENTFLOW_TOKEN')
    if configured:
        if len(configured) < 24:
            raise ValueError('AGENTFLOW_TOKEN must be at least 24 characters')
        return configured
    root = Path(root)
    if root.is_symlink():
        raise PermissionError('symlinked data directory refused')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == 'posix' and root.stat().st_mode & 0o077:
        raise PermissionError('local data directory must be owner-only (chmod 700)')
    token_file = root / 'local-token'
    if token_file.is_symlink():
        raise PermissionError('symlinked token file refused')
    if token_file.exists():
        if os.name == 'posix' and token_file.stat().st_mode & 0o077:
            raise PermissionError('token file must be owner-only (chmod 600)')
        token = token_file.read_text(encoding='ascii').strip()
        if len(token) < 24:
            raise ValueError('invalid existing local token')
        return token
    token = secrets.token_urlsafe(36)
    try:
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return local_token(root)
    with os.fdopen(fd, 'w', encoding='ascii') as output:
        output.write(token + '\n')
    return token


def service_command(service: str, port: int) -> list[str]:
    if service not in ('serve', 'worker'):
        raise ValueError('unsupported service')
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--service', service, '--port', str(port)]
    return [sys.executable, '-m', 'agentflow_runtime.desktop', '--service', service, '--port', str(port)]


def start_local(port: int = 8787, *, browser: bool = True):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('port must be 1024..65535')
    root = data_dir()
    token = local_token(root)
    env = dict(os.environ)
    # Block inherited shared/distributed settings. The desktop runtime should
    # never unexpectedly bind to a remote DB or listen on a non-loopback IP.
    for key in ('AGENTFLOW_POSTGRES_DSN', 'AGENTFLOW_CONTAINER_BIND',
                'AGENTFLOW_GITHUB_SECRET', 'AGENTFLOW_TEST_POSTGRES_DSN'):
        env.pop(key, None)
    env['AGENTFLOW_TOKEN'] = token
    env['AGENTFLOW_DB'] = str(root / 'queue.db')
    http = build_opener(ProxyHandler({}))
    flags = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    children: list[subprocess.Popen] = []
    try:
        # First initialize the database via the API process; starting both
        # services concurrently on an empty SQLite file can race in schema DDL.
        children.append(subprocess.Popen(service_command('serve', port), env=env, **flags))
        url = f'http://127.0.0.1:{port}'
        for _ in range(70):
            if any(child.poll() is not None for child in children):
                raise RuntimeError('local service exited before readiness')
            try:
                with http.open(url + '/health/ready', timeout=0.35) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(.2)
        else:
            raise RuntimeError('local dashboard readiness timed out')
        children.append(subprocess.Popen(service_command('worker', port), env=env, **flags))
        print('AgentFlow dashboard: ' + url, flush=True)
        print('Token file: ' + str(root / 'local-token'), flush=True)
        if browser:
            webbrowser.open(url)
        while all(child.poll() is None for child in children):
            time.sleep(.3)
        raise RuntimeError('local service exited unexpectedly')
    except KeyboardInterrupt:
        return
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)



def self_test() -> dict:
    """Offline end-to-end test for the real frozen executable or source module.

    The isolated test database and bearer token are deleted afterwards.
    There is no browser, network provider, external agent, or remote bind.
    """
    with tempfile.TemporaryDirectory(prefix='agentflow-desktop-smoke-') as folder:
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        env = dict(os.environ)
        for key in ('AGENTFLOW_POSTGRES_DSN','AGENTFLOW_CONTAINER_BIND',
                    'AGENTFLOW_GITHUB_SECRET','AGENTFLOW_TEST_POSTGRES_DSN'):
            env.pop(key, None)
        env['AGENTFLOW_DB'] = str(Path(folder) / 'test.db')
        # pytest's `pythonpath = ["src"]` changes only the test interpreter's
        # import path. Source-mode child services must be able to import this
        # checkout even when the package has not been installed editable yet.
        # Frozen binaries do not need (and must not gain) this source path.
        if not getattr(sys, 'frozen', False):
            source_root = str(Path(__file__).resolve().parents[1])
            inherited = env.get('PYTHONPATH', '')
            env['PYTHONPATH'] = os.pathsep.join(filter(None, (source_root, inherited)))
        token = secrets.token_urlsafe(36)
        env['AGENTFLOW_TOKEN'] = token
        http = build_opener(ProxyHandler({}))
        flags = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
        children=[]
        try:
            children.append(subprocess.Popen(service_command('serve', port), env=env,
                                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**flags))
            root=f'http://127.0.0.1:{port}'
            deadline=time.monotonic()+25
            while time.monotonic() < deadline:
                if any(p.poll() is not None for p in children):
                    raise RuntimeError('desktop service failed before ready')
                try:
                    with http.open(root+'/health/ready',timeout=.3) as response:
                        if response.status == 200:break
                except Exception:
                    time.sleep(.1)
            else:raise RuntimeError('desktop did not become ready')
            children.append(subprocess.Popen(service_command('worker', port), env=env,
                                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**flags))
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
            with http.open(Request(root+'/api/jobs',data=b'{"prompt":"desktop-self-test"}',
                                 headers=headers,method='POST'),timeout=4) as response:
                ident=json.load(response)['id']
            while time.monotonic() < deadline:
                with http.open(Request(root+'/api/jobs/'+ident,headers=headers),timeout=3) as response:
                    job=json.load(response)
                if job['state']=='succeeded':
                    if job['result']!='desktop-self-test':
                        raise RuntimeError('desktop result mismatch')
                    return {'self_test':'PASSED','echo':'succeeded','platform':sys.platform,
                            'frozen':bool(getattr(sys,'frozen',False))}
                if job['state'] in ('failed','uncertain','cancelled'):
                    raise RuntimeError('desktop Echo failed: '+job['state'])
                time.sleep(.1)
            raise TimeoutError('desktop Echo did not complete')
        finally:
            for child in children:
                if child.poll() is None:child.terminate()
            for child in children:
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)


def main(argv=None):
    parser = argparse.ArgumentParser(description='AgentFlow offline local desktop launcher')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--service', choices=['serve', 'worker'])
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    if args.check_only:
        print(json.dumps({'platform': sys.platform, 'frozen': bool(getattr(sys, 'frozen', False)),
                          'local_only': True, 'version': __version__}))
        return 0
    if args.self_test:
        print(json.dumps(self_test()))
        return 0
    if args.service:
        from .cli import main as cli_main
        base = ['agentflow', 'serve', '--port', str(args.port)] if args.service == 'serve' else ['agentflow', 'worker', '--workflows']
        sys.argv = base
        cli_main()
        return 0
    start_local(args.port, browser=not args.no_browser)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
