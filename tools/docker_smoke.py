"""Opt-in live Docker containment check; requires a preloaded digest-pinned image.

Example: python tools/docker_smoke.py --image 'alpine@sha256:...' --command cat
Run on a dedicated trusted test host, not on production or with secrets.
"""
import argparse
from agentflow_runtime.sandbox import DockerSandboxAdapter


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',required=True,help='sha256 digest-pinned preloaded image')
    parser.add_argument('--command',nargs='+',required=True)
    args=parser.parse_args()
    adapter=DockerSandboxAdapter(args.image,args.command)
    actual=adapter('agentflow-sandbox-smoke',10)
    if 'agentflow-sandbox-smoke' not in actual:
        raise RuntimeError('container did not echo expected marker')
    print('Docker smoke: passed; this does not certify hostile multi-tenant isolation')


if __name__=='__main__':main()
