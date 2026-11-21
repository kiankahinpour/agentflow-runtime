"""Run native Windows Job Objects test suite and report its exit code."""
import os,subprocess,sys
from pathlib import Path

def run():
    if os.name!='nt':raise RuntimeError('requires native Windows OS')
    root=Path(__file__).resolve().parents[1]
    cmd=[sys.executable,'-m','pytest','-v','tests/test_v050.py','-k','windows_job_cleans_child']
    outcome=subprocess.run(cmd,cwd=root,timeout=180)
    if outcome.returncode:raise RuntimeError('Windows Job Objects smoke test did not pass')
    return True
if __name__=='__main__':
    run();print('Windows native Job Objects test passed')
