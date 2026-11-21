"""Opt-in authenticated Codex smoke test; may consume account/API quota."""
import argparse, shutil, subprocess, tempfile
from pathlib import Path
from agentflow_runtime.adapters import codex_adapter

def main():
    p=argparse.ArgumentParser();p.add_argument('--allow-live-call',action='store_true');a=p.parse_args()
    if not shutil.which('codex'):p.exit(2,'Codex CLI not installed or not on PATH.\n')
    if not a.allow_live_call:p.exit(2,'Pass --allow-live-call to explicitly authorize a potentially metered Codex request.\n')
    if not shutil.which('git'):p.exit(2,'Git is required for the disposable workspace.\n')
    with tempfile.TemporaryDirectory(prefix='agentflow-live-') as temp:
        root=Path(temp);subprocess.run(['git','init','--quiet',str(root)],check=True)
        text=codex_adapter(root)('Reply with exactly AGENTFLOW_SMOKE_OK, do not modify files.',120)
        if text.strip()!='AGENTFLOW_SMOKE_OK':p.exit(1,'Codex ran, but the expected response marker was not returned.\n')
        print('Live Codex smoke passed.')
if __name__=='__main__':main()
