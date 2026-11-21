"""Private subprocess launcher; Linux subreaper adopts ordinary detached descendants."""
import ctypes
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

CLEANUP_FAILED=125
STOPPED=124

def linux_main(args,ready=None):
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(36,1,0,0,0)!=0:  # PR_SET_CHILD_SUBREAPER
        return CLEANUP_FAILED
    stopped=False
    def stop(*_):
        nonlocal stopped
        stopped=True
    signal.signal(signal.SIGTERM,stop)
    if ready is not None:Path(ready).touch()
    if stopped: return STOPPED
    # Supervisor remains alive while the direct child and adopted children are killed.
    try: child=subprocess.Popen(args)
    except OSError: return 126
    while not stopped and child.poll() is None: time.sleep(.02)
    end=time.monotonic()+4
    children=Path(f'/proc/self/task/{os.getpid()}/children')
    def child_pids():
        try:return [int(p) for p in children.read_text().split()]
        except FileNotFoundError:
            # Some kernels omit CONFIG_CHECKPOINT_RESTORE /proc children.
            found=[]
            for entry in Path('/proc').iterdir():
                if not entry.name.isdecimal():continue
                try:fields=(entry/'stat').read_text().rsplit(')',1)[1].split()
                except (OSError,IndexError):continue
                if len(fields)>1 and fields[1]==str(os.getpid()):found.append(int(entry.name))
            return found
    while time.monotonic()<end:
        try:pids=child_pids()
        except OSError:return CLEANUP_FAILED
        for pid in pids:
            try: os.kill(pid,signal.SIGKILL)
            except ProcessLookupError: pass
        child.poll()
        # Reap adopted children, never steal the direct child's status before poll.
        if child.returncode is not None:
            try:
                while os.waitpid(-1,os.WNOHANG)[0]: pass
            except ChildProcessError:
                if not child_pids():
                    return STOPPED if stopped else (0 if child.returncode==0 else 1)
        time.sleep(.02)
    return CLEANUP_FAILED


def windows_main(gate,args):
    deadline=time.monotonic()+10
    while not Path(gate).exists():
        if time.monotonic()>deadline: return CLEANUP_FAILED
        time.sleep(.02)
    try: return subprocess.call(args)
    except OSError: return 126

if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='linux-ready':sys.exit(linux_main(sys.argv[3:],sys.argv[2]))
    if mode=='linux-gated':
        deadline=time.monotonic()+10
        while not Path(sys.argv[2]).exists():
            if time.monotonic()>deadline:sys.exit(CLEANUP_FAILED)
            time.sleep(.02)
        sys.exit(linux_main(sys.argv[3:]))
    sys.exit(linux_main(sys.argv[2:]) if mode=='linux' else windows_main(sys.argv[2],sys.argv[3:]))
