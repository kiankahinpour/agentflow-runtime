"""Offline, non-mutating publication preflight for the source checkout.

This is a conservative credential-pattern and unsafe-file gate, NOT a complete
secret scanner, dependency audit, signature verifier, or Git history review.
Nothing is pushed or uploaded and no network connection is made.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    'README.md', 'LICENSE', 'CONTRIBUTING.md', 'SECURITY.md',
    'CHANGELOG.md', 'ROADMAP.md', 'pyproject.toml', 'RELEASE_TESTS.md',
    '.gitignore', '.github/workflows/ci.yml', '.github/workflows/release.yml',
)
# Files generated during local development are not included in the source ZIP;
# ignored folders are not a substitute for reviewing `git diff --cached`.
GENERATED_DIRS = {
    '.git', '.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache',
    '.ruff_cache', '.tox', 'build', 'dist', 'dist-native', '_dist-native',
}
PRIVATE_NAMES = {
    '.env', '.netrc', '.npmrc', 'id_rsa', 'id_ed25519', 'local-token',
    'credentials.json', 'service-account.json', 'authorized_keys',
}
PRIVATE_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.pem', '.p12', '.pfx', '.key', '.jks', '.kdbx', '.enc', '.pyc'}
TEXT_SUFFIXES = {
    '.py', '.md', '.txt', '.log', '.json', '.yml', '.yaml', '.toml',
    '.sh', '.bat', '.ps1', '.command', '.html', '.js', '.cfg', '.ini',
    '.csv', '.example', '.service', '.dockerignore', '.gitignore',
}
PATTERNS = {
    'github credential': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{35,})\b'),
    'API credential': re.compile(rb'\b(?:sk-proj-[A-Za-z0-9_-]{35,}|sk-[A-Za-z0-9]{40,}|pypi-[A-Za-z0-9_-]{35,})\b'),
    'AWS access key': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'Slack credential': re.compile(rb'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
    'private key': re.compile(rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
}
# Publication is intentionally prohibited by the bundled artifact workflow.
PUBLISH_MARKERS = ('pypa/gh-action-pypi-publish', 'id-token: write', 'twine upload', 'gh release create')


def check(root: Path = ROOT) -> dict:
    root = Path(root)
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        raise RuntimeError('required publication files missing: ' + ', '.join(missing))
    risks = []
    scanned_text = 0
    examined_files = 0
    for current, dirs, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(current)
        for dirname in list(dirs):
            path = current / dirname
            if path.is_symlink():
                risks.append(f'{path.relative_to(root).as_posix()}: symlinked directory')
                dirs.remove(dirname)
            elif dirname in GENERATED_DIRS or dirname.endswith('.egg-info'):
                dirs.remove(dirname)
        for filename in filenames:
            path = current / filename
            rel = path.relative_to(root).as_posix()
            examined_files += 1
            lower = filename.lower()
            if path.is_symlink():
                risks.append(f'{rel}: symlinked file')
                continue
            if (lower in PRIVATE_NAMES or (lower.startswith('.env.') and lower != '.env.example')
                    or path.suffix.lower() in PRIVATE_SUFFIXES):
                risks.append(f'{rel}: private file name or extension')
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES and filename not in ('Dockerfile', 'SHA256SUMS.txt'):
                continue
            try:
                data = path.read_bytes()
            except OSError as exc:
                risks.append(f'{rel}: cannot read file ({type(exc).__name__})')
                continue
            if b'\x00' in data:
                risks.append(f'{rel}: unexpected binary data in text file')
                continue
            scanned_text += 1
            for label, pattern in PATTERNS.items():
                if pattern.search(data):
                    risks.append(f'{rel}: possible {label}')
    release_workflow = (root / '.github/workflows/release.yml').read_text(encoding='utf-8').lower()
    for marker in PUBLISH_MARKERS:
        if marker in release_workflow:
            risks.append(f'.github/workflows/release.yml: publishing-related marker ({marker})')
    if risks:
        raise RuntimeError('GitHub preflight blocked:\n' + '\n'.join(sorted(set(risks))))
    return {
        'preflight': 'passed', 'publication': 'NOT performed',
        'files_checked': examined_files, 'text_files_scanned': scanned_text,
        'limitations': 'pattern checks only; review staged files, Git history, screenshots and dependencies manually',
    }


def check_staged(root: Path = ROOT) -> dict:
    """Inspect exact Git index blobs, not just potentially different worktree files."""
    root = Path(root)
    command = ['git', '-C', str(root)]
    try:
        entries = subprocess.run(command + ['ls-files', '--stage', '-z'],
                                 capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError('cannot inspect Git index; initialize a Git repository first') from exc
    risks = []
    checked = 0
    for record in entries.split(b'\0'):
        if not record:
            continue
        metadata, raw_name = record.split(b'\t', 1)
        mode = metadata.split(b' ', 1)[0]
        name = raw_name.decode('utf-8', errors='surrogateescape')
        path = Path(name)
        lower = path.name.lower()
        checked += 1
        if mode != b'100644' and mode != b'100755':
            risks.append(f'{name}: non-regular staged Git entry')
            continue
        if (lower in PRIVATE_NAMES or (lower.startswith('.env.') and lower != '.env.example')
                or path.suffix.lower() in PRIVATE_SUFFIXES):
            risks.append(f'{name}: private staged filename or extension')
            continue
        if any(part in GENERATED_DIRS or part.endswith('.egg-info') for part in path.parts[:-1]):
            risks.append(f'{name}: generated directory staged')
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in ('Dockerfile', 'SHA256SUMS.txt'):
            continue
        try:
            blob = subprocess.run(command + ['show', ':' + name], capture_output=True,
                                  check=True).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError(f'cannot read staged blob: {name}') from exc
        if b'\x00' in blob:
            risks.append(f'{name}: unexpected binary staged text')
        for label, pattern in PATTERNS.items():
            if pattern.search(blob):
                risks.append(f'{name}: possible staged {label}')
        if name == '.github/workflows/release.yml':
            for marker in PUBLISH_MARKERS:
                if marker.encode() in blob.lower():
                    risks.append(f'{name}: staged publishing-related marker ({marker})')
    if risks:
        raise RuntimeError('Git index preflight blocked:\n' + '\n'.join(sorted(set(risks))))
    return {'staged_preflight': 'passed', 'staged_entries_checked': checked,
            'publication': 'NOT performed',
            'limitations': 'does not scan Git history, images or all possible credential formats'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='machine-readable result')
    parser.add_argument('--staged', action='store_true', help='also inspect exact Git index content')
    args = parser.parse_args()
    try:
        result = check()
        if args.staged:
            result.update(check_staged())
    except RuntimeError as exc:
        parser.exit(1, f'FAIL: {exc}\n')
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result)


if __name__ == '__main__':
    main()
