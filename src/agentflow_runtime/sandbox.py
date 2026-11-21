"""Opt-in Docker process isolation for *trusted deployments*.

This is defense in depth, NOT a proven hostile multi-tenant boundary. Neither
host Docker socket nor secrets are mounted. Each job runs in an ephemeral,
non-root container with no network, read-only rootfs and bounded resources.
The image must be supplied by digest and preloaded by the operator.
"""
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from .worker import ExecutionStopped

DIGEST_IMAGE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._:/-]*@sha256:[0-9a-f]{64}$')


def secure_docker_args(docker, image, command, container_name, *, cpus=1.0, memory_mb=256):
    if not isinstance(image,str) or not DIGEST_IMAGE.fullmatch(image):
        raise ValueError('sandbox image must be pinned to a sha256 digest')
    if not isinstance(command,(list,tuple)) or not command or any(not isinstance(x,str) or not x or '\x00' in x for x in command):
        raise ValueError('sandbox command must be a nonempty argv list')
    if any(len(x)>4096 for x in command):
        raise ValueError('sandbox argument too long')
    if not re.fullmatch(r'agentflow-[0-9a-f]{32}',container_name):
        raise ValueError('invalid container identifier')
    if not isinstance(cpus,(int,float)) or not .1<=cpus<=4:
        raise ValueError('cpus must be 0.1–4')
    if type(memory_mb) is not int or not 64<=memory_mb<=4096:
        raise ValueError('memory_mb must be 64–4096')
    return [docker, 'run', '--rm', '--pull=never', '-i', '--name',container_name,
            '--network=none', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--user=65534:65534',
            '--pids-limit=64', '--cpus',str(cpus),
            '--memory',f'{memory_mb}m', '--memory-swap',f'{memory_mb}m',
            '--tmpfs','/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777',
            '--init', '--log-driver=none',
            image,*command]


class DockerSandboxAdapter:
    supports_cancellation=True

    def __init__(self, image, command, *, cpus=1.0, memory_mb=256, docker=None):
        self.docker=docker or shutil.which('docker')
        if not self.docker:
            raise RuntimeError('docker CLI is required for sandbox execution')
        self.image=image
        self.command=list(command)
        self.cpus=cpus
        self.memory_mb=memory_mb
        # fail closed at configuration time
        secure_docker_args(self.docker,image,self.command,'agentflow-'+'0'*32,
                           cpus=cpus,memory_mb=memory_mb)

    def _remove(self, name):
        try:
            result=subprocess.run([self.docker,'rm','--force','--volumes',name],
                                   capture_output=True,timeout=10)
        except (OSError,subprocess.TimeoutExpired):
            return False
        if result.returncode==0:return True
        message=(result.stderr or b'').decode('utf-8',errors='replace')
        return 'No such container' in message or 'No such object' in message

    def __call__(self, prompt, timeout, *, cancel_event=None):
        if not isinstance(prompt,str) or len(prompt)>100000:
            raise ValueError('invalid prompt')
        if cancel_event is not None and cancel_event.is_set():
            raise ExecutionStopped()
        name='agentflow-'+uuid.uuid4().hex
        args=secure_docker_args(self.docker,self.image,self.command,name,
                                cpus=self.cpus,memory_mb=self.memory_mb)
        # File-backed stdin/stdout prevent pipe backpressure deadlocks and
        # keep prompt off process argv and command-line history.
        with tempfile.TemporaryFile() as inp,tempfile.TemporaryFile() as out:
            inp.write(prompt.encode('utf-8'));inp.seek(0)
            proc=subprocess.Popen(args,stdin=inp,stdout=out,stderr=subprocess.DEVNULL)
            deadline=time.monotonic()+timeout
            forced=False
            try:
                while proc.poll() is None:
                    if cancel_event is not None and cancel_event.is_set():
                        forced=True
                        if not self._remove(name):
                            raise RuntimeError('sandbox cancellation not confirmed')
                        raise ExecutionStopped()
                    if time.monotonic()>=deadline:
                        forced=True
                        if not self._remove(name):
                            raise RuntimeError('sandbox timeout cleanup unconfirmed')
                        raise TimeoutError('sandbox execution exceeded time limit')
                    if os.fstat(out.fileno()).st_size>2_000_000:
                        forced=True
                        if not self._remove(name):
                            raise RuntimeError('sandbox output limit cleanup unconfirmed')
                        raise RuntimeError('sandbox output exceeded 2 MB')
                    time.sleep(.05)
            finally:
                if proc.poll() is None:
                    if not forced:
                        self._remove(name)
                    try:proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill();proc.wait(timeout=5)
                # A successful Docker CLI exit is not by itself a containment
                # attestation. Confirm removal even on the success path.
                if not self._remove(name):
                    raise RuntimeError('sandbox cleanup could not be confirmed')
            if proc.returncode:
                raise RuntimeError(f'sandbox process exited with status {proc.returncode}')
            out.seek(0);raw=out.read(2_000_001)
            if len(raw)>2_000_000:raise RuntimeError('sandbox output exceeded 2 MB')
            return raw.decode('utf-8',errors='replace')[:100000]
