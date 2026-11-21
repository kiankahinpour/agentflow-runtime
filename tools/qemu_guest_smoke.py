"""Explicit real QEMU boot/serial check; not a security certification."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from agentflow_runtime.vm import QemuVMAdapter

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--image',required=True,help='operator-built qcow2 image')
    p.add_argument('--sha256',required=True)
    p.add_argument('--allow-real-boot',action='store_true')
    p.add_argument('--timeout',type=int,default=180)
    args=p.parse_args()
    if not args.allow_real_boot:p.error('set --allow-real-boot for a disposable, audited VM image')
    if not 1<=args.timeout<=3600:p.error('timeout 1-3600')
    a=QemuVMAdapter(args.image,args.sha256,require_ready=True)
    result=a('AGENTFLOW_VM_ECHO_OK',args.timeout)
    if result!='AGENTFLOW_VM_ECHO_OK':p.exit(1,'guest did not echo expected response')
    print(json.dumps({'status':'passed','qemu_serial_handshake':True,'note':'not a security certification'}))
if __name__=='__main__':main()
