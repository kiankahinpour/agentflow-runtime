import os
import subprocess
import sys
import pytest
from agentflow_runtime.adapters import codex_adapter

@pytest.mark.skipif(os.name=='nt',reason='POSIX executable fixture; Windows needs a separate integration fixture')
def test_codex_fake_executable(tmp_path,monkeypatch):
    exe=tmp_path/'codex'
    exe.write_text('#!'+sys.executable+'\n'+'''import sys
from pathlib import Path
args=sys.argv[1:]
assert args[:3]==['exec','--sandbox','read-only']
assert args[3]=='--output-last-message' and args[-1]=='-'
assert Path.cwd().name=='workspace'
Path(args[4]).write_text(sys.stdin.read(),encoding='utf-8')
''',encoding='utf-8');exe.chmod(0o700)
    root=tmp_path/'workspace';root.mkdir()
    monkeypatch.setenv('PATH',str(tmp_path))
    assert codex_adapter(root)('--dangerously-bypass-approvals-and-sandbox\nسلام',5)=='--dangerously-bypass-approvals-and-sandbox\nسلام'

@pytest.mark.skipif(os.name=='nt',reason='POSIX executable fixture')
@pytest.mark.parametrize('script,error',[('raise SystemExit(3)',RuntimeError),('pass',RuntimeError),('import time;time.sleep(5)',subprocess.TimeoutExpired)])
def test_codex_failure_paths(tmp_path,monkeypatch,script,error):
    exe=tmp_path/'codex';exe.write_text('#!'+sys.executable+'\n'+script+'\n');exe.chmod(0o700)
    monkeypatch.setenv('PATH',str(tmp_path))
    with pytest.raises(error):codex_adapter(tmp_path)('test',.5 if error is subprocess.TimeoutExpired else 5)


@pytest.mark.skipif(os.name == 'nt', reason='POSIX process signal semantics')
def test_posix_group_permission_denial_preserves_uncertainty(monkeypatch):
    """EPERM on SIGKILL must not mask timeout or claim group containment."""
    import agentflow_runtime.adapters as adapters
    sent = []
    class FakeProc:
        pid = 73111
        returncode = None
        leader_killed = False
        def poll(self):
            return self.returncode
        def kill(self):
            self.leader_killed = True
            self.returncode = -9
        def wait(self, timeout):
            assert timeout == 5
            return self.returncode
    proc = FakeProc()
    def fake_killpg(pid, sig):
        sent.append((pid, sig))
        if sig == adapters.signal.SIGKILL:
            raise PermissionError(1, 'Operation not permitted')
    monkeypatch.setattr(adapters.os, 'killpg', fake_killpg)
    monkeypatch.setattr(adapters.time, 'sleep', lambda _: None)
    assert adapters._stop_posix_group(proc) is False
    assert proc.leader_killed
    assert sent == [(proc.pid, adapters.signal.SIGTERM), (proc.pid, adapters.signal.SIGKILL)]


@pytest.mark.skipif(os.name == 'nt', reason='POSIX process signal semantics')
def test_posix_group_permission_denial_cannot_be_claimed_clean(monkeypatch):
    """A clean leader exit is not evidence of descendant cleanup after EPERM."""
    import agentflow_runtime.adapters as adapters
    class FakeProc:
        pid = 73112
        def poll(self): return 0
        def wait(self, timeout): return 0
        def kill(self): raise AssertionError('must not kill completed leader')
    def deny_killpg(pid, sig):
        raise PermissionError(1, 'Operation not permitted')
    monkeypatch.setattr(adapters.os, 'killpg', deny_killpg)
    assert adapters._stop_posix_group(FakeProc()) is False


@pytest.mark.skipif(os.name == 'nt', reason='POSIX process signal semantics')
def test_posix_missing_group_falls_back_to_leader(monkeypatch):
    import agentflow_runtime.adapters as adapters
    class FakeProc:
        pid = 73113
        returncode = None
        def poll(self): return self.returncode
        def kill(self): self.returncode = -9
        def wait(self, timeout): return self.returncode
    monkeypatch.setattr(adapters.os, 'killpg', lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))
    assert adapters._stop_posix_group(FakeProc()) is False


@pytest.mark.skipif(os.name == 'nt', reason='POSIX process signal semantics')
def test_posix_eperm_during_timeout_keeps_original_exception(tmp_path, monkeypatch):
    """Cleanup EPERM must not replace the task's TimeoutExpired error."""
    import agentflow_runtime.adapters as adapters
    class FakeProc:
        pid = 73114
        returncode = None
        def poll(self): return self.returncode
        def wait(self, timeout):
            if self.returncode is None:
                raise subprocess.TimeoutExpired(['dummy'], timeout)
            return self.returncode
        def kill(self): self.returncode = -9
    proc = FakeProc()
    monkeypatch.setattr(adapters.shutil, 'which', lambda exe: '/fake/codex')
    monkeypatch.setattr(adapters, '_launch', lambda *args, **kwargs: (proc, None))
    monkeypatch.setattr(adapters, '_stop_tree', lambda p, job=None: adapters._stop_posix_group(p))
    monkeypatch.setattr(adapters.sys, 'platform', 'darwin')  # exercise caller's macOS semantics
    monkeypatch.setattr(adapters.os, 'killpg', lambda pid, sig: (_ for _ in ()).throw(PermissionError(1, 'EPERM')))
    with pytest.raises(subprocess.TimeoutExpired):
        adapters.codex_adapter(tmp_path)('test', 0.02)
    assert proc.returncode == -9
