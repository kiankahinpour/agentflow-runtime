"""Adversarial archive verification tests."""
import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('verify_release', Path(__file__).resolve().parents[1] / 'tools' / 'verify_release.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def archive(tmp_path, payload=b'ok', name='agentflow-runtime/README.md', manifest=True, extra=()):
    target = tmp_path / 'release.zip'
    with zipfile.ZipFile(target, 'w') as z:
        entry = zipfile.ZipInfo(name)
        # Exercise the verifier with the exact fixture spelling on every OS.
        entry.filename = name
        z.writestr(entry, payload)
        for n, content in extra:
            z.writestr(n, content)
        if manifest:
            z.writestr('agentflow-runtime/SHA256SUMS.txt', hashlib.sha256(payload).hexdigest() + '  README.md\n')
    return target


def test_valid(tmp_path):
    assert module.verify(archive(tmp_path)) == 1


def test_tamper(tmp_path):
    with pytest.raises(ValueError, match='checksum mismatch'):
        module.verify(_tampered(tmp_path))


def _tampered(tmp_path):
    target = archive(tmp_path)
    with zipfile.ZipFile(target, 'w') as z:
        z.writestr('agentflow-runtime/README.md', b'bad')
        z.writestr('agentflow-runtime/SHA256SUMS.txt', hashlib.sha256(b'ok').hexdigest() + '  README.md\n')
    return target


@pytest.mark.parametrize('name', ['../README.md', '/agentflow-runtime/README.md', 'agentflow-runtime/../README.md', 'agentflow-runtime\\README.md'])
def test_unsafe_paths(tmp_path, name):
    with pytest.raises(ValueError, match='unsafe archive path'):
        module.verify(archive(tmp_path, name=name))


def test_unlisted_file(tmp_path):
    with pytest.raises(ValueError, match='manifest mismatch'):
        module.verify(archive(tmp_path, extra=[('agentflow-runtime/extra.txt', b'extra')]))


def test_missing_listed_file(tmp_path):
    target = archive(tmp_path)
    with zipfile.ZipFile(target, 'w') as z:
        z.writestr('agentflow-runtime/SHA256SUMS.txt', hashlib.sha256(b'ok').hexdigest() + '  README.md\n')
    with pytest.raises(ValueError, match='manifest mismatch'):
        module.verify(target)


def test_missing_manifest(tmp_path):
    with pytest.raises(ValueError, match='missing checksum manifest'):
        module.verify(archive(tmp_path, manifest=False))


def test_malformed_archive(tmp_path):
    target = tmp_path / 'release.zip'
    target.write_bytes(b'This file is not a ZIP archive.')
    with pytest.raises(zipfile.BadZipFile):
        module.verify(target)


def test_encrypted_entry_is_rejected_before_content_read(tmp_path, monkeypatch):
    original = zipfile.ZipFile.infolist

    def flagged_entries(archive_file):
        entries = original(archive_file)
        entries[0].flag_bits |= 1
        return entries

    monkeypatch.setattr(zipfile.ZipFile, 'infolist', flagged_entries)
    with pytest.raises(ValueError, match='encrypted archive entry'):
        module.verify(archive(tmp_path))


def test_duplicate_file(tmp_path):
    with pytest.warns(UserWarning):
        target = archive(tmp_path, extra=[('agentflow-runtime/README.md', b'other')])
    with pytest.raises(ValueError, match='duplicate ZIP entry'):
        module.verify(target)


def test_symlink(tmp_path):
    target = archive(tmp_path)
    with zipfile.ZipFile(target, 'w') as z:
        info = zipfile.ZipInfo('agentflow-runtime/link')
        info.create_system = 3
        info.external_attr = (0o120777 << 16)
        z.writestr(info, 'README.md')
        z.writestr('agentflow-runtime/SHA256SUMS.txt', '')
    with pytest.raises(ValueError, match='symlink'):
        module.verify(target)


def test_entry_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'MAX_ENTRY_BYTES', 2)
    with pytest.raises(ValueError, match='oversized archive entry'):
        module.verify(archive(tmp_path, payload=b'123'))


def test_total_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'MAX_ARCHIVE_BYTES', 2)
    with pytest.raises(ValueError, match='total uncompressed size'):
        module.verify(archive(tmp_path, payload=b'123'))


def test_entry_count_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'MAX_ENTRIES', 1)
    with pytest.raises(ValueError, match='too many ZIP entries'):
        module.verify(archive(tmp_path))


def test_release_path_depth_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'MAX_PATH_DEPTH', 1)
    with pytest.raises(ValueError, match='archive path depth'):
        module.verify(archive(tmp_path))


def test_compression_ratio_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'MAX_RATIO', 1)
    target = tmp_path / 'compressed.zip'
    payload = b'0' * 4096
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('agentflow-runtime/README.md', payload)
        z.writestr('agentflow-runtime/SHA256SUMS.txt', hashlib.sha256(payload).hexdigest() + '  README.md\n')
    with pytest.raises(ValueError, match='excessive compression ratio'):
        module.verify(target)


def test_special_file_rejected(tmp_path):
    target = tmp_path / 'special.zip'
    with zipfile.ZipFile(target, 'w') as z:
        info = zipfile.ZipInfo('agentflow-runtime/README.md')
        info.create_system = 3
        info.external_attr = 0o010644 << 16
        z.writestr(info, b'ok')
        z.writestr('agentflow-runtime/SHA256SUMS.txt', hashlib.sha256(b'ok').hexdigest() + '  README.md\n')
    with pytest.raises(ValueError, match='special archive entry'):
        module.verify(target)


def test_manifest_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'MAX_MANIFEST_BYTES', 4)
    with pytest.raises(ValueError, match='oversized checksum manifest'):
        module.verify(archive(tmp_path))
