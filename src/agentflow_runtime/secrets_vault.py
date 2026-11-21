"""Optional encrypted local secret vault for trusted operators (not an untrusted sandbox).

Requires cryptography extras and an externally managed Fernet master key.
At-rest encryption is not a substitute for process isolation or OS keychain ACLs.
"""
import json
import os
import re
import tempfile
from pathlib import Path

SECRET_NAME = re.compile(r'[A-Z][A-Z0-9_]{1,63}\Z')

class EncryptedSecretVault:
    def __init__(self, path, key):
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise RuntimeError('install agentflow-durable[secrets]') from exc
        if not key:raise ValueError('external vault key required')
        self.cipher=Fernet(key.encode('ascii') if isinstance(key,str) else key)
        self.path=Path(path).expanduser().absolute()
        if self.path.is_symlink():raise ValueError('vault symlink refused')
        self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)

    def _read(self):
        if not self.path.exists():return {}
        if self.path.is_symlink():raise ValueError('vault symlink refused')
        if os.name=='posix' and self.path.stat().st_mode & 0o077:
            raise PermissionError('vault permissions must be owner-only (chmod 600)')
        data=json.loads(self.cipher.decrypt(self.path.read_bytes()))
        if not isinstance(data,dict):raise ValueError('invalid vault contents')
        return data

    def get(self, name, allowed_names):
        if not isinstance(name,str) or not SECRET_NAME.fullmatch(name):raise ValueError('invalid secret name')
        if name not in allowed_names:raise PermissionError('secret access not allowed')
        values=self._read()
        if name not in values:raise KeyError('secret does not exist')
        return values[name]

    def set(self, name, value):
        if not isinstance(name,str) or not SECRET_NAME.fullmatch(name):raise ValueError('invalid secret name')
        if not isinstance(value,str) or not value or len(value)>16384:raise ValueError('invalid secret value')
        values=self._read();values[name]=value
        payload=self.cipher.encrypt(json.dumps(values,sort_keys=True).encode())
        descriptor,temporary=tempfile.mkstemp(prefix='.agentflow-vault-',dir=self.path.parent)
        try:
            os.chmod(temporary,0o600)
            with os.fdopen(descriptor,'wb') as output:
                output.write(payload);output.flush();os.fsync(output.fileno())
            if self.path.is_symlink():raise ValueError('vault symlink refused')
            os.replace(temporary,self.path)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
