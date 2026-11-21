"""Verify a requested manual build version against the canonical runtime version.

Does not build, sign, upload, publish, or access any external service.
"""
import argparse
import os
from pathlib import Path
import re
import runpy

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[a-zA-Z0-9.+-]+)?\Z")


def check(requested: str, root=ROOT) -> str:
    if not requested or not VERSION_PATTERN.fullmatch(requested):
        raise ValueError('invalid requested version')
    actual = runpy.run_path(str(Path(root) / 'src/agentflow_runtime/_version.py'))['__version__']
    if requested != actual:
        raise ValueError(f'version mismatch: requested {requested}, source {actual}')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default=None, help='Exact version (otherwise REQUESTED_VERSION env)')
    args = parser.parse_args()
    try:
        actual = check(args.version if args.version is not None else os.environ.get('REQUESTED_VERSION', ''))
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(f'PASS: source version {actual}; manual artifact build only')


if __name__ == '__main__':
    main()
