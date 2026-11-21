"""v1.1.0 offline behavioral tests; native/hosted verification is separate."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agentflow_runtime import __version__
from agentflow_runtime.desktop import data_dir, local_token, main, service_command
from agentflow_runtime.vm import QemuVMAdapter


def test_desktop_local_token_private_and_stable(tmp_path, monkeypatch):
    monkeypatch.delenv('AGENTFLOW_TOKEN', raising=False)
    root = tmp_path / 'private'
    assert local_token(root) == local_token(root)
    assert len(local_token(root)) >= 24
    if os.name == 'posix':
        assert not root.stat().st_mode & 0o077
        assert not (root / 'local-token').stat().st_mode & 0o077


def test_desktop_rejects_unsafe_token(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENTFLOW_TOKEN', 'short')
    with pytest.raises(ValueError):
        local_token(tmp_path)
    monkeypatch.delenv('AGENTFLOW_TOKEN', raising=False)
    if os.name == 'posix':
        link = tmp_path / 'link'
        link.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(PermissionError):
            local_token(link)


def test_desktop_service_command_and_preflight(capsys):
    assert service_command('serve', 8787)[-3:] == ['serve', '--port', '8787']
    assert main(['--check-only']) == 0
    preflight = json.loads(capsys.readouterr().out)
    assert preflight['local_only'] is True
    assert preflight['version'] == __version__
    with pytest.raises(ValueError):
        service_command('external-agent', 8787)


@pytest.mark.skipif(os.name == 'nt', reason='POSIX executable fake VM only')
def test_qemu_long_lived_guest_stops_after_reply(tmp_path):
    image = tmp_path / 'fake-image.qcow2'
    image.write_bytes(b'fake')
    command = tmp_path / 'qemu-test'
    command.write_text(
        '#!' + sys.executable + '\n'
        'import base64,json,sys,time,os\n'
        'print("Linux booting...",flush=True)\n'
        'print("AGENTFLOW_READY",flush=True)\n'
        'data=json.loads(sys.stdin.readline())\n'
        'print("AGENTFLOW_RESULT="+base64.b64encode(data["prompt"].encode()).decode(),flush=True)\n'
        'time.sleep(20)\n', encoding='utf-8')
    command.chmod(0o700)
    adapter = QemuVMAdapter(image, hashlib.sha256(image.read_bytes()).hexdigest(),
                            qemu=str(command), require_ready=True)
    start = time.monotonic()
    assert adapter('VM-REPLIED-OK', 4) == 'VM-REPLIED-OK'
    assert time.monotonic() - start < 3.5  # must not wait for VM shutdown
    cmd = adapter.command()
    assert '-net' in cmd and cmd[cmd.index('-net')+1] == 'none'
    assert '-snapshot' in cmd


@pytest.mark.skipif(os.name == 'nt', reason='POSIX executable fake VM only')
def test_qemu_no_ready_times_out(tmp_path):
    image=tmp_path/'guest.qcow2';image.write_bytes(b'fake')
    command=tmp_path/'qemu-noready'
    command.write_text('#!'+sys.executable+'\nimport time\ntime.sleep(10)\n', encoding='utf-8')
    command.chmod(0o700)
    adapter=QemuVMAdapter(image,hashlib.sha256(image.read_bytes()).hexdigest(),qemu=str(command))
    with pytest.raises(TimeoutError):
        adapter('hello',1)


def test_native_build_manifest_validation():
    from tools.build_native import manifest
    data=manifest('Linux', 'x86_64', 'AgentFlow')
    assert data['publishing'] is False
    assert data['cross_compiled'] is False
    assert data['platform'] == 'Linux'
    assert data['version'] == __version__


def test_desktop_real_source_loopback_smoke(monkeypatch):
    # Test real service orchestration, not a mocked browser/UI endpoint.
    from agentflow_runtime.desktop import self_test
    with socket.socket() as unavailable_proxy:
        unavailable_proxy.bind(('127.0.0.1', 0))
        monkeypatch.setenv('HTTP_PROXY', f'http://127.0.0.1:{unavailable_proxy.getsockname()[1]}')
        monkeypatch.setenv('NO_PROXY', 'other.invalid')
        result = self_test()
    assert result['self_test']=='PASSED' and result['echo']=='succeeded'


def test_provider_preflight_does_not_claim_authentication():
    from tools.provider_matrix import check
    result=check()
    assert set(result)=={'codex','claude','opencode'}
    assert all(v['authenticated']=='UNVERIFIED' and v['execution']=='NOT_RUN' for v in result.values())


def test_docker_postgres_fault_tool_requires_explicit_permission():
    from tools.ci_postgres_fault import run
    with pytest.raises(PermissionError):run()


def test_release_publish_defaults_to_build_only():
    # Since v1.2.9 the manual workflow cannot publish at all. In particular
    # it has no PyPI writer permission or conditional publish job to enable.
    data = (Path(__file__).parents[1] / '.github/workflows/release.yml').read_text()
    assert 'workflow_dispatch:' in data
    assert 'upload-artifact@v4' in data
    assert 'pypa/gh-action-pypi-publish' not in data
    assert 'id-token: write' not in data
    assert 'publish_pypi' not in data
