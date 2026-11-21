"""Offline checkout freshness check for public-beta CI.

This verifies that a checkout contains the specific cross-platform fix markers
and version expected by this workflow. It cannot authenticate Git history,
provide signed provenance, or prove functionality without native test runs.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_version(root: Path) -> str:
    source = (root / 'src/agentflow_runtime/_version.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    raise RuntimeError('missing literal __version__ in src/agentflow_runtime/_version.py')


def check(root: Path = ROOT, *, expected_version: str) -> dict:
    root = Path(root)
    problems = []
    try:
        version = read_version(root)
        if version != expected_version:
            problems.append(f'version mismatch: checked out {version}, expected {expected_version}')
    except (OSError, SyntaxError, RuntimeError) as exc:
        version = None
        problems.append(f'cannot inspect checked-out version: {exc}')
    # These markers intentionally cover the fixes that were previously reported
    # as "pushed" but were absent in the actual GitHub Actions checkout.
    markers = {
        'src/agentflow_runtime/adapters.py': (
            'def _stop_posix_group(', 'except PermissionError:',
        ),
        'tests/test_adapters.py': (
            'test_posix_group_permission_denial_preserves_uncertainty',
        ),
        'tools/prepare_github.py': ('path.relative_to(root).as_posix()',),
        'tests/test_github_publication_preflight.py': (
            'test_relative_path_display_is_posix_even_for_windows_paths',
        ),
    }
    for name, expected_markers in markers.items():
        try:
            contents = (root / name).read_text(encoding='utf-8')
        except OSError:
            problems.append(f'missing or unreadable checkout file: {name}')
            continue
        for marker in expected_markers:
            if marker not in contents:
                problems.append(f'stale checkout code in {name}: missing {marker}')
    if problems:
        raise RuntimeError('CI checkout/source mismatch:\n' + '\n'.join(problems))
    return {
        'status': 'PASS',
        'checked_out_version': version,
        'expected_version': expected_version,
        'critical_files_checked': len(markers) + 1,
        'limitations': 'source markers only; not independent native validation or publisher authentication',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-version', required=True)
    args = parser.parse_args()
    try:
        result = check(expected_version=args.expected_version)
    except RuntimeError as exc:
        parser.exit(1, f'FAIL: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
