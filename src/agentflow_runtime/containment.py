"""Opt-in cgroup-v2 cleanup; requires a dedicated delegated subtree.
Not a security sandbox; untrusted agents must use a separate OS identity/VM.
"""
import time
import uuid
from pathlib import Path

class LinuxCgroup:
    def __init__(self, parent):
        root=Path(parent).resolve(strict=True)
        if not (root/'cgroup.controllers').is_file() or root==Path('/sys/fs/cgroup'):
            raise ValueError('configure a dedicated delegated cgroup v2 subtree, not the mount root')
        self.path=root/('agentflow-'+uuid.uuid4().hex)
        self.path.mkdir()
        try:
            if not (self.path/'cgroup.kill').is_file():raise RuntimeError('cgroup.kill unavailable')
        except BaseException:
            self.path.rmdir();raise
    def attach(self,pid):
        (self.path/'cgroup.procs').write_text(str(pid))
    def stop(self):
        (self.path/'cgroup.kill').write_text('1')
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if 'populated 0' in (self.path/'cgroup.events').read_text().splitlines():return True
            time.sleep(.03)
        return False
    def close(self):
        self.path.rmdir()
