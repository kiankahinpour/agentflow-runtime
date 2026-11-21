"""Run test modules in isolated process groups with bounded wall-clock time.

A timeout is a failure, never a skip or a successful test result.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import threading
import tempfile
from collections import deque
from contextlib import ExitStack

if os.name == 'nt':
    # The guard can run from a source checkout without an editable installation.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
    from agentflow_runtime.adapters import _launch, _stop_tree


def run_module(path, timeout, cwd):
    # Emit the currently running test and a Python traceback before the hard kill.
    # This makes timeout reports actionable rather than merely naming the module.
    diagnostic_delay = max(0.1, timeout * 0.6)
    command = [sys.executable, '-m', 'pytest', '-vv', '-s',
               '-o', f'faulthandler_timeout={diagnostic_delay:.3f}', str(path)]
    start = time.monotonic()
    kwargs = {'cwd': cwd, 'stdin': subprocess.DEVNULL, 'stdout': None, 'stderr': subprocess.STDOUT}
    if os.name == 'posix':
        kwargs['start_new_session'] = True
    timed_out = False
    # Drain stdout concurrently to avoid pipe deadlocks. Retain only the last
    # 12 KiB in memory: large or endless logs cannot fill the host disk.
    tail = deque()
    tail_size = 0
    output_bytes = 0
    lock = threading.Lock()

    def drain(pipe):
        nonlocal tail_size, output_bytes
        try:
            while True:
                chunk = os.read(pipe.fileno(), 8192)
                if not chunk:
                    break
                with lock:
                    output_bytes += len(chunk)
                    tail.append(chunk)
                    tail_size += len(chunk)
                    while tail_size > 12000:
                        excess = tail_size - 12000
                        first = tail.popleft()
                        if len(first) > excess:
                            tail.appendleft(first[excess:])
                            tail_size -= excess
                        else:
                            tail_size -= len(first)
        except (OSError, ValueError):
            pass

    kwargs['stdout'] = subprocess.PIPE
    cleanup_error = None
    with ExitStack() as resources:
        job = None
        if os.name == 'nt':
            folder = resources.enter_context(tempfile.TemporaryDirectory(prefix='agentflow-guard-'))
            proc, job = _launch(command, cwd, subprocess.DEVNULL, folder,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            resources.callback(job.close)
        else:
            proc = subprocess.Popen(command, **kwargs)
        try:
            reader = threading.Thread(target=drain, args=(proc.stdout,), daemon=True)
            reader.start()
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if job is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
        finally:
            if job is not None:
                try:
                    if not _stop_tree(proc, job):
                        cleanup_error = 'Windows Job Object still had active processes'
                except (OSError, subprocess.TimeoutExpired) as exc:
                    cleanup_error = str(exc)
                finally:
                    job.close()
        # A detached descendant on POSIX may keep stdout open.
        reader.join(timeout=1.0)
        with lock:
            output = b''.join(tail).decode('utf-8', errors='replace')
            captured_bytes = output_bytes
        proc.stdout.close()
    status = 'timeout' if timed_out else ('passed' if proc.returncode == 0 and not cleanup_error else 'failed')
    result = {'module': str(path),
              'status': status,
              'returncode': proc.returncode,
              'seconds': round(time.monotonic()-start, 2),
              'output_bytes': captured_bytes,
              'output_truncated': captured_bytes > 12000,
              'output': output}
    if cleanup_error:
        result['cleanup_error'] = cleanup_error
    return result


def write_report(path, results, complete=False, running_module=None):
    """Persist progress atomically after every module, including failed modules.

    Interrupted runs retain their last completed module instead of losing the
    entire report. A false `complete` is not a successful regression run.
    """
    path = Path(path)
    report = {'complete': complete, 'running_module': running_module, 'results': results,
              'passed_modules': sum(r['status'] == 'passed' for r in results),
              'failed_modules': sum(r['status'] == 'failed' for r in results),
              'timed_out_modules': sum(r['status'] == 'timeout' for r in results)}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=90)
    parser.add_argument('--report', default='regression-guard-report.json')
    parser.add_argument('--fail-fast', action='store_true', help='Stop after first failed or timed-out module; retain incomplete report')
    parser.add_argument('modules', nargs='*')
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error('timeout must be positive')
    root = Path(__file__).resolve().parents[1]
    tests_dir = (root/'tests').resolve()
    modules = [Path(p).resolve() for p in args.modules] if args.modules else sorted(tests_dir.glob('test_*.py'))
    for module in modules:
        if not module.is_file() or not module.is_relative_to(tests_dir):
            parser.error(f'not a test module inside tests/: {module}')
    results = []
    write_report(args.report, results, complete=False)
    for module in modules:
        write_report(args.report, results, complete=False, running_module=str(module))
        result = run_module(module, args.timeout, root)
        results.append(result)
        write_report(args.report, results, complete=False)
        print(f"{result['status'].upper()}: {module.name} ({result['seconds']}s)", flush=True)
        if args.fail_fast and result['status'] != 'passed':
            return 1
    write_report(args.report, results, complete=True)
    return 0 if all(r['status']=='passed' for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
