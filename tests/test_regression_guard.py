"""Tests for bounded regression execution and reliable failure reporting."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('regression_guard', ROOT/'tools'/'regression_guard.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_passed_module(tmp_path):
    file = tmp_path/'test_ok.py'
    file.write_text('def test_ok(): assert True\n')
    result = mod.run_module(file, 15, tmp_path)
    assert result['status'] == 'passed'


def test_failed_module(tmp_path):
    file = tmp_path/'test_fail.py'
    file.write_text('def test_fail(): assert False\n')
    result = mod.run_module(file, 15, tmp_path)
    assert result['status'] == 'failed'


def test_timeout_kills_descendants(tmp_path):
    if sys.platform != 'linux':
        import pytest
        pytest.skip('Linux process-group integration')
    file = tmp_path/'test_hang.py'
    file.write_text('import time\ndef test_hang(): time.sleep(60)\n')
    result = mod.run_module(file, 0.7, tmp_path)
    assert result['status'] == 'timeout'
    assert result['seconds'] < 8


def test_timeout_report_identifies_hanging_test(tmp_path):
    if sys.platform != 'linux':
        import pytest
        pytest.skip('Linux diagnostic integration')
    file = tmp_path/'test_named_hang.py'
    file.write_text('import time\ndef test_specific_hang(): time.sleep(60)\n')
    result = mod.run_module(file, 2.5, tmp_path)
    assert result['status'] == 'timeout'
    assert 'test_specific_hang' in result['output']
    assert 'test_named_hang.py::test_specific_hang' in result['output']


def test_large_output_is_bounded(tmp_path):
    file = tmp_path/'test_large.py'
    file.write_text("def test_large():\n    print('X' * 250000)\n    assert True\n")
    result = mod.run_module(file, 15, tmp_path)
    assert result['status'] == 'passed'
    assert result['output_truncated'] is True
    assert result['output_bytes'] > 200000
    assert len(result['output'].encode()) <= 12003


def test_streaming_output_has_no_disk_spool(tmp_path, monkeypatch):
    # Regression guard must not use tempfile-backed output storage.
    import tempfile
    def forbidden(*args, **kwargs):
        raise AssertionError('disk spool is forbidden')
    monkeypatch.setattr(tempfile, 'TemporaryFile', forbidden)
    file = tmp_path/'test_stream.py'
    file.write_text("def test_stream():\n    print('Z' * 400000)\n")
    result = mod.run_module(file, 15, tmp_path)
    assert result['status'] == 'passed'
    assert result['output_bytes'] > 400000
    assert result['output_truncated']


def test_report_is_atomic_and_marks_incomplete(tmp_path):
    import json
    report = tmp_path/'nested'/'progress.json'
    result = {'module': 'test_x.py', 'status': 'timeout'}
    mod.write_report(report, [result])
    data = json.loads(report.read_text())
    assert data['complete'] is False
    assert data['timed_out_modules'] == 1
    assert not list(report.parent.glob('*.tmp'))
    mod.write_report(report, [result], complete=True)
    assert json.loads(report.read_text())['complete'] is True


def test_report_replace_failure_preserves_previous_report(tmp_path, monkeypatch):
    import json
    report = tmp_path/'report.json'
    mod.write_report(report, [], complete=False)
    previous = report.read_bytes()
    def fail_replace(*args):
        raise OSError('simulated atomic replace failure')
    monkeypatch.setattr(mod.os, 'replace', fail_replace)
    import pytest
    with pytest.raises(OSError):
        mod.write_report(report, [{'status': 'passed'}], complete=True)
    assert report.read_bytes() == previous
    assert not list(tmp_path.glob('*.tmp'))


def test_report_tracks_inflight_module(tmp_path):
    import json
    path = tmp_path/'report.json'
    mod.write_report(path, [], running_module='tests/test_stalled.py')
    data = json.loads(path.read_text())
    assert data['complete'] is False
    assert data['running_module'] == 'tests/test_stalled.py'
    mod.write_report(path, [{'status': 'passed'}], complete=True)
    assert json.loads(path.read_text())['running_module'] is None

def test_child_stdin_is_closed(tmp_path, monkeypatch):
    original = mod.subprocess.Popen
    observed = []
    def capture(*args, **kwargs):
        observed.append(kwargs.get('stdin'))
        return original(*args, **kwargs)
    monkeypatch.setattr(mod.subprocess, 'Popen', capture)
    file = tmp_path/'test_ok.py'
    file.write_text('def test_ok(): assert True\n')
    assert mod.run_module(file, 15, tmp_path)['status'] == 'passed'
    assert observed == [mod.subprocess.DEVNULL]


def test_fail_fast_preserves_incomplete_evidence(tmp_path, monkeypatch):
    import json
    report = tmp_path / 'report.json'
    first = ROOT / 'tests' / 'test_core.py'
    second = ROOT / 'tests' / 'test_api.py'
    invoked = []
    def fake_run(module, timeout, cwd):
        invoked.append(module)
        return {'module': str(module), 'status': 'timeout', 'seconds': 1, 'returncode': -9}
    monkeypatch.setattr(mod, 'run_module', fake_run)
    assert mod.main(['--fail-fast', '--report', str(report), str(first), str(second)]) == 1
    data = json.loads(report.read_text())
    assert data['complete'] is False
    assert data['timed_out_modules'] == 1
    assert data['running_module'] is None
    assert invoked == [first]
