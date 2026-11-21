"""Explicitly authorized real-provider smoke; no automatic install or login."""
import argparse, tempfile, subprocess, shutil
from pathlib import Path
from agentflow_runtime.adapters import codex_adapter
from agentflow_runtime.external import cli_adapter
from agentflow_runtime.ollama import ollama_adapter

def main():
    p=argparse.ArgumentParser();p.add_argument('provider',choices=['codex','claude','opencode','ollama']);p.add_argument('--model');p.add_argument('--port',type=int,default=11434);p.add_argument('--allow-live-call',action='store_true');a=p.parse_args()
    if not a.allow_live_call:p.error('explicit --allow-live-call required; request may consume provider quota')
    if a.provider=='ollama' and not a.model:p.error('--model must specify a locally installed model')
    if a.provider!='ollama' and not shutil.which(a.provider):p.error(a.provider+' CLI absent from PATH')
    with tempfile.TemporaryDirectory(prefix='agentflow-live-') as d:
        root=Path(d)
        if a.provider=='codex':
            subprocess.run(['git','init','--quiet',d],check=True);adapter=codex_adapter(root)
        elif a.provider=='ollama':adapter=ollama_adapter(a.model,a.port)
        else:adapter=cli_adapter(a.provider,root)
        result=adapter('Reply with exactly AGENTFLOW_SMOKE_OK. Do not call tools or modify files.',120)
        if result.strip()!='AGENTFLOW_SMOKE_OK':p.exit(1,'Provider responded, but expected marker was not returned.\n')
        print(f'{a.provider}: authenticated/local live smoke passed.')
if __name__=='__main__':main()
