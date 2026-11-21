"""Provider preflight, with opt-in smoke. Never claims login from PATH checks.

Real calls can consume provider quotas. Nothing runs unless operator explicitly
passes both --allow-live-calls and --accept-provider-costs.
"""
import argparse
import json
import shutil
import subprocess
import sys

PROVIDERS=('codex','claude','opencode')


def check():
    return {name: {'cli_installed':bool(shutil.which(name)), 'authenticated':'UNVERIFIED',
                   'execution':'NOT_RUN'} for name in PROVIDERS}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--provider',choices=PROVIDERS,action='append')
    p.add_argument('--allow-live-calls',action='store_true')
    p.add_argument('--accept-provider-costs',action='store_true')
    args=p.parse_args()
    data=check()
    if args.allow_live_calls != args.accept_provider_costs:
        p.error('both --allow-live-calls and --accept-provider-costs are required')
    if args.allow_live_calls:
        for name in (args.provider or PROVIDERS):
            if not data[name]['cli_installed']:
                data[name]['execution']='NOT_RUN_CLI_MISSING'
                continue
            try:
                result=subprocess.run([sys.executable,'tools/live_provider_smoke.py',name,'--allow-live-call'],
                                      capture_output=True,timeout=180,check=False)
                data[name]['execution']='PASS' if result.returncode==0 else 'FAIL'
            except subprocess.TimeoutExpired:
                data[name]['execution']='TIMEOUT'
    print(json.dumps(data,indent=2))
    return 0 if not args.allow_live_calls or all(data[n]['execution']=='PASS' for n in (args.provider or PROVIDERS)) else 1
if __name__=='__main__':raise SystemExit(main())
