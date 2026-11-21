"""v1.0.0 safety/cross-platform offline contracts; native host checks remain explicit."""
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from agentflow_runtime.api import create_app
from agentflow_runtime.store import Store
from agentflow_runtime.secrets_vault import EncryptedSecretVault
from agentflow_runtime.vm import QemuVMAdapter
from tools.start_local import local_token, check

KEY='test-audit-hmac-key-very-long-and-unique-string-001'


def test_audit_signing_detects_modification(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENTFLOW_AUDIT_HMAC_KEY',KEY)
    store=Store(tmp_path/'db.sqlite')
    store.audit('alice','approve','job-1')
    store.audit('bob','cancel','job-2')
    proof=store.audit_verify()
    assert proof['verified'] and proof['signed']==2 and proof['unsigned_legacy']==0
    tip=proof['tip']
    assert store.audit_verify(tip)['expected_tip_matched']
    with store.tx() as c:
        c.execute("UPDATE audit_records SET action='succeeded' WHERE seq=1")
    assert not store.audit_verify()['verified']


def test_audit_signing_rejects_partial_record_removal(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENTFLOW_AUDIT_HMAC_KEY',KEY)
    s=Store(tmp_path/'db.sqlite');s.audit('alice','submit','one');s.audit('alice','submit','two')
    checkpoint=s.audit_verify()['tip']
    with s.tx() as c:c.execute('DELETE FROM audit_records WHERE seq=1')
    assert s.audit_verify()['verified'] is False
    with s.tx() as c:c.execute('DELETE FROM audit_integrity WHERE seq=1')
    assert s.audit_verify()['verified'] is False
    # Even deletion of last signed event is detected with an external checkpoint.
    with s.tx() as c:c.execute('DELETE FROM audit_records WHERE seq=2');c.execute('DELETE FROM audit_integrity WHERE seq=2')
    assert not s.audit_verify(checkpoint)['verified']


def test_audit_reports_unsigned_legacy(tmp_path,monkeypatch):
    monkeypatch.delenv('AGENTFLOW_AUDIT_HMAC_KEY',raising=False)
    db=tmp_path/'db.sqlite';Store(db).audit('legacy','submit','old')
    monkeypatch.setenv('AGENTFLOW_AUDIT_HMAC_KEY',KEY)
    newer=Store(db);newer.audit('alice','submit','new')
    assert newer.audit_verify()['unsigned_legacy']==1
    assert newer.audit_verify()['signed']==1


def test_audit_is_protected_for_tenant_nonadmin(tmp_path):
    from agentflow_runtime.tenants import create_tenant_app
    user='x'*40
    config={'alpha':[{'sha256':hashlib.sha256(user.encode()).hexdigest(),'role':'viewer'}]}
    client=TestClient(create_tenant_app(tmp_path,config))
    assert client.get('/t/alpha/api/audit/verify',headers={'Authorization':'Bearer '+user}).status_code==403


def test_vault_encryption_allowed_names_and_symlink(tmp_path):
    key=Fernet.generate_key()
    vault=EncryptedSecretVault(tmp_path/'vault.enc',key)
    vault.set('CODEX_API_KEY','secret-value')
    assert b'secret-value' not in (tmp_path/'vault.enc').read_bytes()
    assert vault.get('CODEX_API_KEY',{'CODEX_API_KEY'})=='secret-value'
    with pytest.raises(PermissionError):vault.get('CODEX_API_KEY',{'OTHER_KEY'})
    with pytest.raises(ValueError):vault.set('../../evil','secret-value')
    if os.name=='posix':
        (tmp_path/'vault.enc').chmod(0o644)
        with pytest.raises(PermissionError):vault.get('CODEX_API_KEY',{'CODEX_API_KEY'})
        (tmp_path/'vault.enc').chmod(0o600)
        link=tmp_path/'link.enc'
        link.symlink_to(tmp_path/'vault.enc')
        with pytest.raises(ValueError):EncryptedSecretVault(link,key)


def test_guest_contract():
    from guest.agentflow_guest import process
    assert process(json.dumps({'prompt':'سلام'}).encode())=='سلام'
    with pytest.raises(ValueError):process(json.dumps({'prompt':'a','code':'rm -rf /'}).encode())


@pytest.mark.skipif(os.name=='nt',reason='POSIX fake-QEMU executable; Windows native QEMU pending')
def test_guest_ready_handshake_fake_binary(tmp_path):
    img=tmp_path/'guest.qcow2';img.write_bytes(b'fake-offline-image')
    fake=tmp_path/'qemu-fake';fake.write_text('#!'+sys.executable+'\nimport sys,base64,json\nprint("AGENTFLOW_READY",flush=True)\nline=sys.stdin.readline()\nprompt=json.loads(line)["prompt"]\nprint("AGENTFLOW_RESULT="+base64.b64encode(prompt.encode()).decode(),flush=True)\n')
    fake.chmod(0o700)
    adapter=QemuVMAdapter(img,hashlib.sha256(img.read_bytes()).hexdigest(),qemu=str(fake),require_ready=True)
    assert adapter('ready-handshake',3)=='ready-handshake'


def test_audit_endpoint_and_platform_check(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENTFLOW_AUDIT_HMAC_KEY',KEY)
    store=Store(tmp_path/'db.sqlite')
    token='s'*40
    app=TestClient(create_app(store,token))
    assert app.get('/api/audit/verify').status_code==401
    response=app.post('/api/jobs',json={'prompt':'hello'},headers={'Authorization':'Bearer '+token})
    assert response.status_code==201
    verify=app.get('/api/audit/verify',headers={'Authorization':'Bearer '+token}).json()
    assert verify['verified'] and verify['signed']==1
    assert check()['mode']=='localhost-only'


def test_local_token_persisted_private_and_no_env_leak(tmp_path,monkeypatch):
    monkeypatch.delenv('AGENTFLOW_TOKEN',raising=False)
    t1=local_token(tmp_path);t2=local_token(tmp_path)
    assert t1==t2 and len(t1)>=24
    if os.name=='posix':assert not (tmp_path/'local-token').stat().st_mode & 0o077


def test_migration_6_and_public_api_version(tmp_path):
    s=Store(tmp_path/'db.sqlite')
    with s.tx() as c:assert c.execute('PRAGMA user_version').fetchone()[0]==6
    token='z'*40
    client=TestClient(create_app(s,token))
    response=client.get('/api/runtime',headers={'Authorization':'Bearer '+token})
    from agentflow_runtime import __version__
    assert response.json()['version'] == __version__
    assert client.app.version == __version__
    assert f'v{__version__}' in client.get('/').text
