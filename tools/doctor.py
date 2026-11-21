"""Read-only capability detector; never assumes installed CLI implies authentication."""
import argparse
import importlib.util
import json
import os
import platform
import shutil
import sys


def report():
    supported=sys.version_info >=(3,10) and sys.platform.startswith(('linux','win32','darwin'))
    tools={name:bool(shutil.which(name)) for name in ('docker','qemu-system-x86_64','codex','claude','opencode','ollama')}
    return {
        'os':platform.system(), 'os_release':platform.release(), 'python':platform.python_version(),
        'python_supported':sys.version_info>=(3,10), 'host_supported':supported,
        'runtime':{'sqlite':True, 'fastapi':bool(importlib.util.find_spec('fastapi')),
                   'postgres_driver':bool(importlib.util.find_spec('psycopg')),
                   'encryption':bool(importlib.util.find_spec('cryptography'))},
        'executables':tools,
        'codex_authenticated':'UNVERIFIED',
        'docker_daemon':'UNVERIFIED',
        'postgres_connection':'UNVERIFIED',
        'qemu_guest_isolation':'UNVERIFIED',
        'untrusted_multi_tenant_execution':'DISABLED',
        'note':'Presence checks are not execution/security certifications.'
    }

def main():
    p=argparse.ArgumentParser();p.add_argument('--json',action='store_true');a=p.parse_args()
    r=report()
    print(json.dumps(r,indent=2) if a.json else '\n'.join(f'{k}: {v}' for k,v in r.items()))
    return 0 if r['host_supported'] else 1
if __name__=='__main__':raise SystemExit(main())
