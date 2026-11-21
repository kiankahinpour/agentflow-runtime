"""Native host verification wrapper, returns nonzero on failed tests."""
import argparse
import subprocess
import sys
import json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--with-native',action='store_true',help='run native OS checks in addition to the standard suite')
    args=p.parse_args()
    project=Path(__file__).resolve().parents[1]
    print('Host:',sys.platform,'Python:',sys.version.split()[0],flush=True)
    tests=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=project)
    if tests.returncode:return tests.returncode
    if args.with_native and sys.platform=='win32':
        return subprocess.run([sys.executable,'tools/windows_native_smoke.py'],cwd=project).returncode
    if args.with_native and sys.platform.startswith('linux'):
        # No privileged or destructive checks without explicit operator action.
        print('Linux native cgroup/VM/Docker tests require separately configured CI resources.')
    if args.with_native and sys.platform=='darwin':
        print('macOS host tests passed; native QEMU/providers require independent opt-in live checks.')
    return 0
if __name__=='__main__':raise SystemExit(main())
