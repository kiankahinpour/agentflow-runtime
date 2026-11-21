# Security design and remaining trust boundaries — v1.0.0 candidate

**This is NOT a security certification.** Restricted tenant mode continues to disable external AI agents. Local operator mode can run trusted subprocesses; Docker and VM adapters are experimental opt-ins.

## Threat model
- Trusted operator controls the host and adapter definitions. Remote API input is never interpreted as a shell command by the built-in adapter.
- Untrusted issues, pull requests and LLM output may contain prompt injection. Human approval is mandatory for non-Echo API submissions; approval is not a substitute for sandboxing.
- Other processes with host privileges, Docker socket access, root/admin access or VM hypervisor compromise are **outside** the containment guarantee.
- Network/egress policy is opt-in for the explicit broker; subprocess-based agents can still access network unless isolated independently.

## Tamper-evident audit
- Set `AGENTFLOW_AUDIT_HMAC_KEY` to an unpredictable **32+ byte** secret stored OUTSIDE the database. On write, a transaction appends HMAC-SHA256 over each record plus the previous MAC.
- `agentflow audit-verify` or authenticated `/api/audit/verify` validates the signed chain. Historical unsigned rows are reported as legacy.
- Record the `tip` returned by the verifier in a physically independent log. `agentflow audit-verify --expected-tip <TIP>` detects a truncated suffix; without an independently stored tip a privileged database editor can delete the tail without detection.
- Changing/losing the key makes existing signatures unverifiable. This is tamper-EVIDENT, not tamper-proof, and does not prevent privileged users from suppressing future audit writes. For high-assurance deployments use external write-once logs and key custody.

## Secret storage
- `EncryptedSecretVault` offers an optional Fernet-encrypted file backed by a separately managed master key. See `[secrets]` extra.
- Use explicit per-name allowlists; never pass secrets into untrusted plugin environments. Key rotation, access revocation, cloud KMS/HSM, Windows DPAPI and macOS Keychain integration are **not** implemented.
- Never commit `.env`, local-token, vault files, API tokens or decrypted outputs. The vault must be protected with restrictive filesystem ACLs.

## VM reference guest
- The `guest/` reference demonstrates a serial protocol with `AGENTFLOW_READY` then `AGENTFLOW_RESULT=<base64>`. It only echoes text; it does **not** execute arbitrary model-generated code.
- `guest/build_guest.sh` customizes a trusted operator-supplied Debian cloud qcow2 with libguestfs tools. QEMU boots with `-net none` and no host mounts. The resulting image is NOT prebuilt nor verified here; boot, console device, guest OS security and guest/protocol integration require validation on a dedicated host.
- SHA-256 pins the guest contents but **does not prove** the kernel/image is safe. Prefer a reviewed immutable image, minimal packages, no cloud credentials, and a clean VM per task.

## Cross-platform
- Windows Job Objects and macOS process groups are process-management controls, not virtual machines.
- On macOS, cancellation of trusted subprocesses can be uncertain if they detach or continue after the parent exits.
- Docker daemon privileges are powerful; never mount the Docker socket into an untrusted task.

## Known gaps
- No audited real QEMU VM isolation / Docker containment certification, live provider authentication, tenant-level subprocess sandbox, independent pen test or multi-region deployment validation.
- Database credentials/DSN and task contents are still sensitive; use least-privilege operators and encrypted disks.
- Audit and rate limiting are not designed as a public Internet DDoS defense.
