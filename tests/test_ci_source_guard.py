"""Offline source-consistency checks for GitHub's native CI runners."""
from pathlib import Path

import pytest
from tools.ci_source_guard import ROOT, check, read_version


def test_current_checkout_contains_expected_version_and_fixes():
    report = check(expected_version='1.3.5')
    assert report['checked_out_version'] == '1.3.5'
    assert report['critical_files_checked'] == 5


def test_incorrect_expected_version_rejected():
    with pytest.raises(RuntimeError, match='version mismatch'):
        check(expected_version='0.0.0')


def test_missing_fix_marker_rejected(tmp_path):
    # Isolate a minimal fixture from the checked-out source to ensure that a
    # partial file copy is detected rather than silently treated as passing.
    (tmp_path / 'src/agentflow_runtime').mkdir(parents=True)
    (tmp_path / 'src/agentflow_runtime/_version.py').write_text('__version__ = "1.3.5"\n')
    with pytest.raises(RuntimeError, match='missing or unreadable checkout file'):
        check(tmp_path, expected_version='1.3.5')


def test_read_version_returns_literal_from_file():
    assert read_version(ROOT) == '1.3.5'


def test_ci_workflow_runs_checkout_guard_before_tests():
    workflow = (ROOT / '.github/workflows/ci.yml').read_text()
    assert 'python tools/ci_source_guard.py --expected-version 1.3.5' in workflow
    assert workflow.index('python tools/ci_source_guard.py') < workflow.index('python -m pytest -q')
    assert 'fail-fast: false' in workflow
