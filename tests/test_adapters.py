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
