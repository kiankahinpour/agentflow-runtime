"""Experimental, operator-enabled Claude Code and OpenCode CLI adapters."""
import os, shutil, subprocess, tempfile, time
from pathlib import Path
from .adapters import _launch, _stop_tree
from .worker import ExecutionStopped


def cli_adapter(name,workspace):
    if name not in ('claude','opencode'):raise ValueError('unsupported CLI adapter')
    root=Path(workspace).expanduser().resolve(strict=True)
    if not root.is_dir():raise ValueError('workspace must be a directory')
    exe=shutil.which(name)
    if not exe:raise RuntimeError(name+' CLI not found on PATH')
    if os.name=='nt' and Path(exe).suffix.lower() in ('.bat','.cmd'):raise RuntimeError('use a native executable, not a shell wrapper')
    if __import__('sys').platform not in ('darwin',) and os.name not in ('nt',) and not __import__('sys').platform.startswith('linux'):raise RuntimeError('unsupported platform')
    # No shell or permission bypass flags. The operator must trust local configuration.
    def run(prompt,timeout,*,cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():raise ExecutionStopped()
        with tempfile.TemporaryDirectory(prefix='agentflow-cli-') as tmp, tempfile.TemporaryFile() as inp, tempfile.TemporaryFile() as out:
            if name=='claude':
                args=[exe,'--print','--output-format','text','--permission-mode','plan','--tools','']
                inp.write(prompt.encode('utf-8'));inp.seek(0)
            else:
                # OpenCode documented positional message; visible in process argv.
                if len(prompt.encode('utf-8'))>8000 or prompt.startswith('-'):raise ValueError('OpenCode prompt exceeds 8000 bytes or begins with a flag')
                args=[exe,'run','--standalone',prompt]
            proc,job=_launch(args,root,inp,tmp,stdout=out)
            deadline=time.monotonic()+timeout;cleaned=False
            try:
                while proc.poll() is None:
                    if cancel_event is not None and cancel_event.is_set():
                        confirmed=_stop_tree(proc,job);cleaned=True
                        if confirmed:raise ExecutionStopped()
                        raise RuntimeError('CLI cancellation unconfirmed')
                    if os.fstat(out.fileno()).st_size>2_000_000:raise RuntimeError('CLI output exceeds 2 MB')
                    if time.monotonic()>=deadline:raise subprocess.TimeoutExpired(args[:2],timeout)
                    time.sleep(.05)
            finally:
                try:
                    if not cleaned and not _stop_tree(proc,job):raise RuntimeError('CLI cleanup unconfirmed')
                finally:
                    if job is not None:job.close()
            if proc.returncode:raise RuntimeError(f'{name} exited with status {proc.returncode}')
            out.seek(0);data=out.read(2_000_001)
            if len(data)>2_000_000:raise RuntimeError('CLI output exceeds 2 MB')
            result=data.decode('utf-8',errors='replace').strip()
            if not result:raise RuntimeError('CLI returned no output')
            return result[:100000]
    run.supports_cancellation=True
    return run
