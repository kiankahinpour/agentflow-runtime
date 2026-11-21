"""Trusted local adapters. No shell interpolation or danger-full-access."""
import os
import shutil
import signal
import subprocess
import tempfile
import time
import sys
from pathlib import Path
from .worker import ExecutionStopped

def echo(prompt, timeout):
    return prompt

def _stop_tree(proc, job=None):
    """Confirm containment when possible, otherwise report uncertainty."""
    if job is not None:
        confirmed=job.stop();proc.wait(timeout=5);return confirmed
    if sys.platform.startswith('linux'):
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                proc.wait(timeout=5);return False
        return proc.returncode in (0,1,124)
    if os.name=='posix':
        return _stop_posix_group(proc)
    if proc.poll() is None:proc.kill()
    proc.wait(timeout=5)
    return False



def _stop_posix_group(proc):
    """Best-effort macOS/POSIX process-group cleanup; never attest descendants.

    A group signal may fail with EPERM if a descendant changes ownership or
    the runner denies signalling it. The caller must still reap the leader and
    preserve the original timeout exception; cancellation remains uncertain.
    Only the Popen leader is eligible for the fallback signal.
    """
    finished_cleanly = proc.poll() == 0
    group_uncertain = False
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            # No signalable process group with this ID; it might have exited.
            break
        except PermissionError:
            # EPERM does not prove the group was terminated. Avoid hiding the
            # adapter's TimeoutExpired with an unrelated cleanup exception.
            group_uncertain = True
            break
        if sig == signal.SIGTERM:
            time.sleep(.05)
    if proc.poll() is None:
        # The group may have been inaccessible or terminated only partly.
        # Target the process object, never a guessed PID/process group.
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            raise RuntimeError('cannot terminate adapter leader after group cleanup') from exc
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('adapter leader still alive after process-group cleanup') from exc
    # Even when the leader exited cleanly, detached descendants are not
    # contained by process groups; EPERM makes the outcome less certain.
    return finished_cleanly and not group_uncertain


def _launch(args, root, input_file, temp, stdout=None, *, stderr=subprocess.DEVNULL):
    stdout=subprocess.DEVNULL if stdout is None else stdout
    supervisor=str(Path(__file__).with_name('_supervisor.py'))
    if sys.platform.startswith('linux') and os.environ.get('AGENTFLOW_CGROUP_ROOT'):
        from .containment import LinuxCgroup
        job=LinuxCgroup(os.environ['AGENTFLOW_CGROUP_ROOT'])
        gate=Path(temp)/'launch.gate'
        proc=None
        try:
            proc=subprocess.Popen([sys.executable,supervisor,'linux-gated',str(gate),*args],stdin=input_file,cwd=root,stdout=stdout,stderr=stderr,start_new_session=True)
            job.attach(proc.pid);gate.touch();return proc,job
        except BaseException:
            try:
                if proc is not None and proc.poll() is None: proc.kill();proc.wait(timeout=5)
                job.stop()
            finally:job.close()
            raise
    if sys.platform.startswith('linux'):
        ready=Path(temp)/'supervisor.ready'
        proc=subprocess.Popen([sys.executable,supervisor,'linux-ready',str(ready),*args],stdin=input_file,cwd=root,stdout=stdout,stderr=stderr,start_new_session=True)
        try:
            deadline=time.monotonic()+10
            while not ready.exists():
                if proc.poll() is not None or time.monotonic()>=deadline:raise RuntimeError('Linux supervisor startup unconfirmed')
                time.sleep(.01)
            return proc,None
        except BaseException:
            _stop_tree(proc);raise
    elif os.name=='nt':
        from .windows_job import WindowsJob
        gate=Path(temp)/'launch.gate'
        proc=subprocess.Popen([sys.executable,supervisor,'windows',str(gate),*args],stdin=input_file,cwd=root,stdout=stdout,stderr=stderr)
        job=None
        try:
            job=WindowsJob(proc.pid);gate.touch();return proc,job
        except BaseException:
            if job is not None:job.close()
            if proc.poll() is None:proc.kill()
            proc.wait(timeout=5);raise
    return subprocess.Popen(args,stdin=input_file,cwd=root,stdout=stdout,stderr=stderr,start_new_session=(os.name=='posix')),None

def codex_adapter(workspace):
    root=Path(workspace).expanduser().resolve(strict=True)
    if not root.is_dir(): raise ValueError('workspace must be a directory')
    executable=shutil.which('codex')
    if not executable: raise RuntimeError('Codex CLI not found on PATH')
    def run(prompt, timeout, *, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set(): raise ExecutionStopped()
        with tempfile.TemporaryDirectory(prefix='agentflow-') as tmp:
            output=Path(tmp)/'last.txt'
            args=[executable,'exec','--sandbox','read-only','--output-last-message',str(output),'-']
            # File-backed stdin avoids pipe deadlock and keeps prompts out of argv.
            with tempfile.TemporaryFile() as input_file:
                input_file.write(prompt.encode('utf-8'));input_file.seek(0)
                proc,job=_launch(args,root,input_file,tmp)
                deadline=time.monotonic()+timeout
                cleaned=False
                try:
                    while proc.poll() is None:
                        if cancel_event is not None and cancel_event.is_set():
                            confirmed=_stop_tree(proc,job);cleaned=True
                            if confirmed: raise ExecutionStopped()
                            raise RuntimeError('process-tree cancellation could not be fully verified')
                        remaining=deadline-time.monotonic()
                        if remaining<=0: raise subprocess.TimeoutExpired(args,timeout)
                        try: proc.wait(timeout=min(.05,remaining))
                        except subprocess.TimeoutExpired: pass
                finally:
                    # Also clean children left behind by a completed/failed leader on POSIX.
                    try:
                        if not cleaned:
                            confirmed=_stop_tree(proc,job)
                            if (job is not None or sys.platform.startswith('linux')) and not confirmed:
                                raise RuntimeError('process-tree cleanup could not be confirmed')
                    finally:
                        if job is not None:job.close()
            if proc.returncode: raise RuntimeError(f'Codex exited with status {proc.returncode}')
            if not output.is_file(): raise RuntimeError('Codex did not write a final response')
            with output.open(encoding='utf-8',errors='replace') as f:return f.read(100000)
    run.supports_cancellation=True
    return run
