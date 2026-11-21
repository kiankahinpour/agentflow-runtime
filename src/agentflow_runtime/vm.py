"""Opt-in reference QEMU executor, not an attested security boundary.

Guest emits READY and one result over the serial console. A normal Linux guest
keeps running after the service sends its result: the *host* must stop QEMU on
receipt rather than waiting for the VM to power off.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from .worker import ExecutionStopped

MARKER = b'AGENTFLOW_RESULT='
READY = b'AGENTFLOW_READY'
ERROR = b'AGENTFLOW_ERROR='
SHA256 = re.compile(r'[a-f0-9]{64}\Z')
MAX_CONSOLE = 2_000_000


class QemuVMAdapter:
    supports_cancellation = True

    def __init__(self, guest_image, expected_sha256, *, qemu=None, ram_mb=256,
                 cores=1, require_ready=True):
        if os.name == 'nt':
            raise RuntimeError('QEMU VM adapter requires Linux/macOS host; Windows not validated')
        if not isinstance(expected_sha256, str) or not SHA256.fullmatch(expected_sha256):
            raise ValueError('sha256 digest required')
        source = Path(guest_image).expanduser()
        if source.is_symlink():
            raise ValueError('symlink guest images forbidden')
        guest = source.resolve(strict=True)
        if not guest.is_file() or guest.stat().st_size > 10 * 1024**3:
            raise ValueError('guest image invalid')
        if type(ram_mb) is not int or not 128 <= ram_mb <= 2048 or type(cores) is not int or not 1 <= cores <= 2:
            raise ValueError('invalid VM resource limits')
        digest = hashlib.sha256()
        with guest.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != expected_sha256:
            raise ValueError('guest image checksum mismatch')
        self.guest = str(guest)
        self.qemu = qemu or shutil.which('qemu-system-x86_64')
        if not self.qemu:
            raise RuntimeError('qemu-system-x86_64 is required')
        self.ram_mb, self.cores, self.require_ready = ram_mb, cores, bool(require_ready)

    def command(self):
        return [self.qemu, '-machine', 'q35,accel=tcg', '-m', str(self.ram_mb),
                '-smp', str(self.cores), '-display', 'none', '-monitor', 'none',
                '-serial', 'stdio', '-no-reboot', '-nodefaults', '-net', 'none',
                '-snapshot', '-drive',
                f'file={self.guest},if=virtio,format=qcow2,snapshot=on']

    def __call__(self, prompt, timeout, *, cancel_event=None):
        if (not isinstance(prompt, str) or not 0 < len(prompt) <= 100000
                or type(timeout) not in (int, float) or not 1 <= timeout <= 3600):
            raise ValueError('invalid VM execution input')
        if cancel_event is not None and cancel_event.is_set():
            raise ExecutionStopped()
        payload = json.dumps({'prompt': prompt}, ensure_ascii=False).encode() + b'\n'
        # QEMU is intentionally destroyed after one successful guest response.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stdin:
            if not self.require_ready:
                stdin.write(payload)
                stdin.seek(0)
            proc = subprocess.Popen(
                self.command(), stdin=subprocess.PIPE if self.require_ready else stdin,
                stdout=stdout, stderr=subprocess.DEVNULL, start_new_session=True)
            offset = 0
            pending = b''
            sent = not self.require_ready
            saw_ready = False
            result = None
            result_count = 0
            deadline = time.monotonic() + timeout
            try:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise ExecutionStopped()
                    if time.monotonic() >= deadline:
                        raise TimeoutError('VM execution timeout')
                    if os.fstat(stdout.fileno()).st_size > MAX_CONSOLE:
                        raise RuntimeError('VM console output limit')
                    stdout.seek(offset)
                    chunk = stdout.read(min(65536, MAX_CONSOLE - offset + 1))
                    offset += len(chunk)
                    pending += chunk
                    # Consume complete serial lines; Linux boot messages may
                    # appear between protocol markers and are ignored.
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        line = line.rstrip(b'\r')
                        if line == READY:
                            saw_ready = True
                        elif line.startswith(ERROR):
                            raise RuntimeError('guest returned error')
                        elif line.startswith(MARKER):
                            result_count += 1
                            if result_count > 1:
                                raise RuntimeError('ambiguous guest response')
                            try:
                                response = base64.b64decode(line[len(MARKER):], validate=True)
                                result = response.decode('utf-8')
                            except (ValueError, UnicodeError) as exc:
                                raise RuntimeError('invalid guest response') from exc
                            if len(result) > 100000:
                                raise RuntimeError('guest result length limit')
                    if self.require_ready and saw_ready and not sent:
                        try:
                            proc.stdin.write(payload)
                            proc.stdin.flush()
                            proc.stdin.close()
                        except (BrokenPipeError, OSError) as exc:
                            raise RuntimeError('guest serial input closed') from exc
                        sent = True
                    if result is not None:
                        if not sent:
                            raise RuntimeError('guest response before request')
                        # Valid reply is enough. VM is not expected to exit.
                        return result
                    if proc.poll() is not None:
                        raise RuntimeError(f'QEMU exited without guest result (status {proc.returncode})')
                    time.sleep(.05)
            finally:
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                if proc.stdin is not None and not proc.stdin.closed:
                    proc.stdin.close()
