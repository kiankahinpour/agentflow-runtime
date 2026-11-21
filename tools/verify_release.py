"""Verify an AgentFlow source archive without extracting untrusted paths."""
import argparse
import hashlib
import ntpath
import re
import sys
import zipfile
from pathlib import PureWindowsPath

MAX_ENTRY_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_ENTRIES = 10000
MAX_RATIO = 1000
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_PATH_DEPTH = 64

DIGEST = re.compile(r"([0-9a-f]{64})  (.+)\Z")
WINDOWS_FORBIDDEN = re.compile(r'[<>:"\\|?*\x00-\x1f]')


def _archive_parts(name):
    path = name[:-1] if name.endswith('/') else name
    parts = path.split('/')
    if len(parts) > MAX_PATH_DEPTH:
        raise ValueError(f'unsafe archive path depth: {len(parts)}')
    is_reserved = getattr(ntpath, 'isreserved', None)
    for part in parts:
        reserved = is_reserved(part) if is_reserved else PureWindowsPath(part).is_reserved()
        if (not part or part.endswith((' ', '.')) or WINDOWS_FORBIDDEN.search(part)
                or reserved):
            raise ValueError(f'unsafe archive path: {name}')
    return tuple(parts)


def verify(archive):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) > MAX_ENTRIES:
            raise ValueError("too many ZIP entries")
        if len(names) != len(set(names)):
            raise ValueError('duplicate ZIP entry')
        files = {}
        paths = {}
        seen = set()
        total_bytes = 0
        for info in z.infolist():
            # ZipInfo.filename normalizes backslashes on Windows and drops NUL
            # suffixes. Validate the spelling recorded in the central directory.
            name = info.orig_filename
            parts = _archive_parts(name)
            directory = name.endswith('/')
            if parts[0] != 'agentflow-runtime' or (len(parts) == 1 and not directory):
                raise ValueError(f'unexpected archive root: {name}')
            full_key = tuple(part.casefold() for part in parts)
            if full_key in seen:
                raise ValueError(f'duplicate ZIP entry: {name}')
            seen.add(full_key)
            for length in range(1, len(parts) + 1):
                key = full_key[:length]
                entry = (parts[:length], directory or length < len(parts))
                if paths.setdefault(key, entry) != entry:
                    raise ValueError(f'conflicting archive path: {name}')
            file_type = (info.external_attr >> 16) & 0o170000
            if file_type == 0o120000:
                raise ValueError(f'symlink archive entry: {name}')
            if file_type not in (0, 0o100000, 0o040000):
                raise ValueError(f'special archive entry: {name}')
            if info.flag_bits & 1:
                raise ValueError(f'encrypted archive entry: {name}')
            if directory:
                if info.file_size:
                    raise ValueError(f'directory entry contains data: {name}')
                continue
            if info.file_size > MAX_ENTRY_BYTES:
                raise ValueError(f'oversized archive entry: {name}')
            total_bytes += info.file_size
            if total_bytes > MAX_ARCHIVE_BYTES:
                raise ValueError('archive exceeds total uncompressed size limit')
            if info.file_size > MAX_RATIO * max(1, info.compress_size):
                raise ValueError(f'excessive compression ratio: {name}')
            files['/'.join(parts[1:])] = info
        manifest = files.get('SHA256SUMS.txt')
        if manifest is None:
            raise ValueError('missing checksum manifest')
        if manifest.file_size > MAX_MANIFEST_BYTES:
            raise ValueError('oversized checksum manifest')
        entries = {}
        for line in z.read(manifest).decode('utf-8').splitlines():
            match = DIGEST.fullmatch(line)
            if not match or match[2] in entries:
                raise ValueError('invalid or duplicate checksum entry')
            entries[match[2]] = match[1]
        actual = set(files) - {'SHA256SUMS.txt'}
        if set(entries) != actual:
            raise ValueError(f'manifest mismatch: missing={sorted(actual-set(entries))}, extra={sorted(set(entries)-actual)}')
        for path in sorted(actual):
            with z.open(files[path]) as stream:
                hasher = hashlib.sha256()
                count = 0
                while chunk := stream.read(1024 * 1024):
                    count += len(chunk)
                    if count > MAX_ENTRY_BYTES:
                        raise ValueError(f'oversized extracted entry: {path}')
                    hasher.update(chunk)
                digest = hasher.hexdigest()
            if digest != entries[path]:
                raise ValueError(f'checksum mismatch: {path}')
        return len(actual)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    args = parser.parse_args()
    try:
        count = verify(args.archive)
    except (OSError, ValueError, zipfile.BadZipFile, UnicodeError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    print(f'PASS: {count} checksum-verified source files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
