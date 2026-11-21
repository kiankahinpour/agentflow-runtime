"""Windows validation with local Python processes and disposable SQLite files."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

from agentflow_runtime import ExecutionStopped, Store
from agentflow_runtime import adapters, external


def test_migration_error_rolls_back_changes(tmp_path, monkeypatch):
    database = tmp_path / 'old.db'
    original = Store(database)
    task = original.submit('keep this task')
    with original.tx() as connection:
        connection.execute('DROP TABLE workers')
        connection.execute('DROP TABLE api_rate_limits')
        connection.execute('PRAGMA user_version=3')

    connect = Store.connect

    def fail_migration(store):
        connection = connect(store)
        connection.set_authorizer(
            lambda action, table, *_: sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_CREATE_TABLE and table == 'api_rate_limits'
            else sqlite3.SQLITE_OK
        )
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(Store, 'connect', fail_migration)
        with pytest.raises(sqlite3.DatabaseError, match='not authorized'):
            Store(database)
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute('PRAGMA user_version').fetchone() == (3,)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name IN ('workers', 'api_rate_limits')"
        ).fetchall() == []
    for _ in range(2):
        assert Store(database).get(task)['prompt'] == 'keep this task'


def test_corrupt_sqlite_snapshot_cleans_destination(tmp_path):
    snapshot = tmp_path / 'corrupt.db'
    snapshot.write_bytes(b'not a sqlite database')
    destination = tmp_path / 'restored.db'
    with pytest.raises(sqlite3.DatabaseError, match='not a database'):
        Store.restore(snapshot, destination)
    assert list(tmp_path.iterdir()) == [snapshot]


def test_uncommitted_write_is_rolled_back_after_process_kill(tmp_path):
    database = tmp_path / 'queue.db'
    store = Store(database)
    task = store.submit('committed task')
    marker = tmp_path / 'transaction-open'
    program = """
import sqlite3, sys, time
from pathlib import Path
connection = sqlite3.connect(sys.argv[1], isolation_level=None)
connection.execute('BEGIN IMMEDIATE')
connection.execute("UPDATE jobs SET prompt='uncommitted change' WHERE id=?", (sys.argv[3],))
Path(sys.argv[2]).touch()
time.sleep(20)
"""
    process = subprocess.Popen([sys.executable, '-c', program, str(database), str(marker), task])
    try:
        deadline = time.monotonic() + 8
        while not marker.exists():
            assert process.poll() is None
            assert time.monotonic() < deadline
            time.sleep(.02)
        process.kill()
        process.wait(timeout=5)
        reopened = Store(database)
        assert reopened.get(task)['prompt'] == 'committed task'
        with closing(sqlite3.connect(database)) as connection:
            assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        print(json.dumps({'killed_writer_pid': process.pid, 'exit_code': process.returncode,
                          'committed_data_preserved': True, 'integrity': 'ok'}))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def windows_kernel():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


LOCAL_FIXTURE = """
from pathlib import Path
import os
import subprocess
import sys
import time

role, folder, output, mode = sys.argv[1:]
root = Path(folder)

def mark(name, text):
    temporary = root / (name + '.tmp')
    temporary.write_text(str(text), encoding='utf-8')
    temporary.replace(root / name)

if role != 'grandchild':
    next_role = {'leader': 'child', 'child': 'grandchild'}[role]
    subprocess.Popen([sys.executable, __file__, next_role, folder, output, mode])
mark(role, os.getpid())
if role == 'leader' and mode == 'leader_exit':
    deadline = time.monotonic() + 15
    while not (root / 'finish').exists() and time.monotonic() < deadline:
        time.sleep(.02)
    assert sys.stdin.read() == 'offline fixture prompt'
    Path(output).write_text('local fixture response', encoding='utf-8')
else:
    time.sleep(20)
"""


@pytest.mark.skipif(os.name != 'nt', reason='Windows process handles and Job Objects required')
@pytest.mark.parametrize('mode', ['cancel', 'timeout', 'leader_exit'])
def test_windows_codex_adapter_tree_exits(tmp_path, monkeypatch, mode):
    script = tmp_path / 'local fixture.py'
    script.write_text(LOCAL_FIXTURE, encoding='utf-8')
    monkeypatch.setattr(adapters.shutil, 'which', lambda name: sys.executable if name == 'codex' else None)
    temp_root = tmp_path / 'adapter temp'
    temp_root.mkdir()
    monkeypatch.setattr(adapters.tempfile, 'tempdir', str(temp_root))
    native_launch = adapters._launch

    def launch_fixture(args, root, input_file, temp):
        assert args == [sys.executable, 'exec', '--sandbox', 'read-only', '--output-last-message',
                        str(Path(temp) / 'last.txt'), '-']
        command = [sys.executable, str(script), 'leader', str(tmp_path), args[5], mode]
        process, job = native_launch(command, root, input_file, temp)
        (tmp_path / 'supervisor').write_text(str(process.pid), encoding='utf-8')
        return process, job

    monkeypatch.setattr(adapters, '_launch', launch_fixture)
    run = adapters.codex_adapter(tmp_path)
    interrupt = threading.Event()
    kernel = windows_kernel()
    roles = ('supervisor', 'leader', 'child', 'grandchild')
    with ThreadPoolExecutor(max_workers=1) as pool, ExitStack() as handles:
        future = pool.submit(run, 'offline fixture prompt', 7 if mode == 'timeout' else 16,
                             cancel_event=interrupt)
        try:
            deadline = time.monotonic() + 6
            while not all((tmp_path / role).exists() for role in roles):
                if future.done():
                    future.result()
                assert time.monotonic() < deadline, 'local process tree did not start'
                time.sleep(.02)
            pids = {role: int((tmp_path / role).read_text()) for role in roles}
            watched = {}
            for role, pid in pids.items():
                handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
                assert handle, ctypes.WinError(ctypes.get_last_error())
                handles.callback(kernel.CloseHandle, handle)
                assert kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT
                watched[role] = handle
            if mode == 'cancel':
                interrupt.set()
                with pytest.raises(ExecutionStopped):
                    future.result(timeout=12)
            elif mode == 'timeout':
                with pytest.raises(subprocess.TimeoutExpired):
                    future.result(timeout=12)
            else:
                (tmp_path / 'finish').touch()
                assert future.result(timeout=12) == 'local fixture response'
            exited = {role: kernel.WaitForSingleObject(handle, 2000) == 0
                      for role, handle in watched.items()}
            print(json.dumps({'mode': mode, 'pids': pids, 'exited': exited}))
            assert all(exited.values())
            assert not list(temp_root.iterdir())
        finally:
            interrupt.set()


def test_short_soak_releases_database_handles():
    from tools.soak import run

    report = run(seconds=1, workers=1, rate=2)
    assert report['states'] == {'succeeded': 2}
    assert report['integrity'] == 'ok'


@pytest.mark.skipif(os.name != 'nt', reason='Windows Job Object integration')
@pytest.mark.parametrize('name', ['claude', 'opencode'])
@pytest.mark.parametrize('failure', [False, True])
def test_windows_external_adapter_uses_local_fixture(tmp_path, monkeypatch, name, failure):
    monkeypatch.setattr(external.shutil, 'which', lambda requested: sys.executable
                        if requested == name else None)
    native_launch = external._launch
    prompt = 'offline contract validation'

    def local_launch(args, root, input_file, temp, stdout):
        if name == 'claude':
            assert args == [sys.executable, '--print', '--output-format', 'text',
                            '--permission-mode', 'plan', '--tools', '']
            command = [sys.executable, '-c', 'import sys; print(sys.stdin.read().strip())']
        else:
            assert args == [sys.executable, 'run', '--standalone', prompt]
            command = [sys.executable, '-c', 'import sys; print(sys.argv[1])', args[3]]
        if failure:
            command[2] += '; sys.exit(7)'
        return native_launch(command, root, input_file, temp, stdout=stdout)

    monkeypatch.setattr(external, '_launch', local_launch)
    adapter = external.cli_adapter(name, tmp_path)
    if failure:
        with pytest.raises(RuntimeError, match='exited with status 7'):
            adapter(prompt, 8)
    else:
        assert adapter(prompt, 8) == prompt


@pytest.mark.skipif(os.name != 'nt', reason='Windows Job Object integration')
def test_windows_guard_timeout_reaps_child_and_captures_diagnostics(tmp_path):
    from tools.regression_guard import run_module

    marker = tmp_path / 'guard-child'
    test = tmp_path / 'test_transient.py'
    test.write_text("""
import subprocess, sys, time
from pathlib import Path

def test_slow():
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(16)'])
    pending = Path(__file__).with_name('guard-child.tmp')
    pending.write_text(str(process.pid))
    pending.replace(pending.with_suffix(''))
    try:
        time.sleep(18)
    finally:
        process.terminate()
        process.wait(timeout=5)
""", encoding='utf-8')

    kernel = windows_kernel()
    with ThreadPoolExecutor(max_workers=1) as pool, ExitStack() as handles:
        execution = pool.submit(run_module, test, 8, tmp_path)
        deadline = time.monotonic() + 6
        while not marker.exists():
            assert time.monotonic() < deadline and not execution.done()
            time.sleep(.03)
        pid = int(marker.read_text())
        process = kernel.OpenProcess(0x00100000, False, pid)
        assert process, ctypes.WinError(ctypes.get_last_error())
        handles.callback(kernel.CloseHandle, process)
        assert kernel.WaitForSingleObject(process, 0) == 258
        report = execution.result(timeout=22)
        stopped = kernel.WaitForSingleObject(process, 0) == 0
        print(json.dumps({'guard_child_pid': pid, 'guard_child_exited': stopped,
                          'status': report['status'], 'seconds': report['seconds']}))
        assert stopped and report['status'] == 'timeout'
        assert not report.get('cleanup_error')
        assert 'test_transient.py::test_slow' in report['output']


def test_parallel_api_submissions_preserve_idempotency(tmp_path):
    from fastapi.testclient import TestClient
    from agentflow_runtime.api import create_app

    store = Store(tmp_path / 'api.db')
    token = 'synthetic-qa-token-not-a-secret'
    with TestClient(create_app(store, token)) as client:
        auth = {'Authorization': f'Bearer {token}'}
        assert client.post('/api/recover').status_code == 401
        assert client.post('/api/jobs', headers=auth, json={'prompt': ''}).status_code == 422

        def submit(index):
            return client.post('/api/jobs', headers=auth, json={
                'prompt': f'synthetic task {index}',
                'idem': f'key-{index}',
            })

        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(submit, list(range(8)) * 2))
        assert all(response.status_code == 201 for response in responses)
        identifiers = [response.json()['id'] for response in responses]
        assert len(set(identifiers)) == 8 and identifiers[:8] == identifiers[8:]
        cancelled = client.post(f'/api/jobs/{identifiers[0]}/cancel', headers=auth)
        assert cancelled.json()['state'] == 'cancelled'
        assert client.get(f'/api/jobs/{identifiers[0]}', headers=auth).json()['state'] == 'cancelled'
        audit = client.get('/api/audit', headers=auth)
        assert audit.status_code == 200 and token not in audit.text


@pytest.mark.parametrize('setting,expected', [(None, '127.0.0.1'), ('1', '0.0.0.0')])
def test_cli_bind_arguments_without_opening_socket(tmp_path, monkeypatch, setting, expected):
    import uvicorn
    from agentflow_runtime.cli import main

    if setting is None:
        monkeypatch.delenv('AGENTFLOW_CONTAINER_BIND', raising=False)
    else:
        monkeypatch.setenv('AGENTFLOW_CONTAINER_BIND', setting)
    monkeypatch.setenv('AGENTFLOW_TOKEN', 'synthetic-qa-token-not-a-secret')
    monkeypatch.setattr(sys, 'argv', ['agentflow', '--db', str(tmp_path / 'bind.db'),
                                     'serve', '--port', '8192'])
    calls = []
    monkeypatch.setattr(uvicorn, 'run', lambda app, **kwargs: calls.append(kwargs))
    main()
    assert calls == [{'host': expected, 'port': 8192, 'access_log': False}]
