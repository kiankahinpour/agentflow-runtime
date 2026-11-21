# Experimental QEMU VM adapter (v0.9.0)

**Not security-certified and not verified with a real guest image.** It is a running code path with offline protocol tests, not a production hostile-code runner.

The VM adapter uses a pre-provisioned QCOW2 guest image pinned by a full SHA-256 hash. The image must contain a trusted guest service whose console reads a single UTF-8 JSON line with `{"prompt":"..."}` and writes exactly one `AGENTFLOW_RESULT=<base64-utf8>` line before shutting down. The guest image and service are **not distributed** in this repository; operators must build and audit them separately. Do not point the adapter at arbitrary third-party images.

The host uses QEMU software emulation (TCG), no guest network, no mounted host workspace/credentials, an ephemeral snapshot overlay, bounded vCPU/RAM, a process timeout and a 2MB console-output cap. Timeouts and cancellations kill the QEMU process group on POSIX. An attacker who escapes the VM or compromises QEMU is outside the guarantees of this prototype. Restrict the host account, apply OS hardening and keep QEMU patched.

Example for an independently audited image on Linux:

```sh
sha256sum /absolute/path/guest.qcow2
agentflow worker --vm-image /absolute/path/guest.qcow2 --vm-sha256 THE_64_HEX_DIGEST
agentflow serve --enable-vm
agentflow submit 'hello' --adapter vm
agentflow approve JOB_ID
```

The guest must understand the serial protocol. Missing guest protocol, timeout or failure is surfaced as an uncertain result requiring inspection. Real VM isolation tests and adversarial validation remain pending.
