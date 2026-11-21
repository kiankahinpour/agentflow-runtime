"""Small Windows benchmark using synthetic work and local SQLite only."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import ctypes
from ctypes import wintypes
import json
import math
from pathlib import Path
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time

from agentflow_runtime import ExecutionStopped, Store, Worker
from benchmark import run as run_queue
from fault_worker_smoke import CHILD


def summarize(samples):
    ordered = sorted(samples)
    return {
        'n': len(ordered),
        'p50_ms': round(statistics.median(ordered), 3),
        'p95_ms': round(ordered[math.ceil(0.95 * len(ordered)) - 1], 3),
        'min_ms': round(ordered[0], 3),
        'max_ms': round(ordered[-1], 3),
        'samples_ms': [round(value, 3) for value in samples],
    }


def elapsed_ms(start):
    return (time.perf_counter() - start) * 1000


def serial_samples(path, count):
    store = Store(path)
    startup, completed, submission, db_lookup = [], [], [], []

    def timed_echo(prompt, timeout):
        startup.append(elapsed_ms(start))
        return prompt

    worker = Worker(store, {'echo': timed_echo})
    for index in range(count):
        prompt = f'synthetic echo {index}'
        start = time.perf_counter()
        job = store.submit(prompt)
        submission.append(elapsed_ms(start))
        assert worker.once()
        completed.append(elapsed_ms(start))
        lookup_start = time.perf_counter()
        result = store.get(job)
        db_lookup.append(elapsed_ms(lookup_start))
        assert result['state'] == 'succeeded' and result['result'] == prompt
    return {label: summarize(values) for label, values in {
        'submit_to_adapter': startup, 'submit_to_worker_return': completed,
        'sqlite_submit': submission, 'sqlite_get': db_lookup,
    }.items()}


def cancellation_samples(path, count):
    store = Store(path)
    results = []

    def cooperative_echo(prompt, timeout, *, cancel_event):
        ready.set()
        if cancel_event.wait(timeout=12):
            raise ExecutionStopped()
        raise TimeoutError('cancel event did not arrive')

    cooperative_echo.supports_cancellation = True
    for _ in range(count):
        ready = threading.Event()
        job = store.submit('synthetic cancellation')
        worker = Worker(store, {'echo': cooperative_echo}, lease=0.9)
        with ThreadPoolExecutor(max_workers=1) as executor:
            execution = executor.submit(worker.once)
            assert ready.wait(timeout=8)
            start = time.perf_counter()
            assert store.cancel(job) == 'cancel_requested'
            assert execution.result(timeout=10)
            results.append(elapsed_ms(start))
        assert store.get(job)['state'] == 'cancelled'
    return summarize(results)


def recovery_samples(directory, count):
    results, processes = [], []
    for index in range(count):
        database = directory / f'recovery-{index}.db'
        marker = directory / f'worker-{index}-ready'
        store = Store(database)
        job = store.submit('synthetic recovery', max_attempts=1)
        process = subprocess.Popen([sys.executable, '-c', CHILD, str(database), str(marker)])
        try:
            deadline = time.monotonic() + 10
            while not marker.exists():
                assert time.monotonic() < deadline and process.poll() is None
                time.sleep(.015)
            assert store.get(job)['state'] == 'running'
            start = time.perf_counter()
            process.kill()
            process.wait(timeout=5)
            deadline = time.monotonic() + 8
            while not store.recover_expired():
                assert time.monotonic() < deadline
                time.sleep(.025)
            results.append(elapsed_ms(start))
            assert store.get(job)['state'] == 'uncertain'
            assert store.claim(['echo'], 0.8) is None
            with closing(sqlite3.connect(database)) as connection:
                assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)
            processes.append({'pid': process.pid, 'exit_code': process.returncode})
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    return {**summarize(results), 'workers': processes}


def memory_mib():
    class ProcessMemory(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (field, ctypes.c_size_t) for field in ('PeakWorkingSetSize', 'WorkingSetSize',
                'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')
        ]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    metrics = ProcessMemory()
    metrics.cb = ctypes.sizeof(metrics)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(metrics), metrics.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {
        'working_set_mib': round(metrics.WorkingSetSize / 2**20, 2),
        'process_lifetime_peak_working_set_mib': round(metrics.PeakWorkingSetSize / 2**20, 2),
    }


def main():
    if sys.platform != 'win32':
        raise SystemExit('This benchmark requires Windows.')
    baseline_memory = memory_mib()
    with tempfile.TemporaryDirectory(prefix='agentflow-windows-bench-') as folder:
        directory = Path(folder)
        wall_start, cpu_start = time.perf_counter(), time.process_time()
        serial = serial_samples(directory / 'serial.db', 100)
        concurrent = [run_queue(200, 4) for _ in range(3)]
        cpu_elapsed = time.process_time() - cpu_start
        wall_elapsed = time.perf_counter() - wall_start
        workload_memory = memory_mib()
        cancellation = cancellation_samples(directory / 'cancel.db', 20)
        recovery = recovery_samples(directory, 5)
    print(json.dumps({
        'platform': sys.platform, 'python': sys.version.split()[0], 'sqlite': sqlite3.sqlite_version,
        'serial_echo': serial, 'concurrent_echo': concurrent,
        'cancel_to_worker_return': cancellation, 'force_kill_to_uncertain': recovery,
        'measured_process_resources': {
            'scope': 'Python process including worker threads, serial and concurrent Echo only',
            'before': baseline_memory, 'after': workload_memory,
            'cpu_seconds': round(cpu_elapsed, 3), 'wall_seconds': round(wall_elapsed, 3),
            'percent_of_one_logical_cpu': round(100 * cpu_elapsed / wall_elapsed, 2),
        },
    }, indent=2))


if __name__ == '__main__':
    main()
