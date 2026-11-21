## Current release support and private reporting (v1.3.1)

The v1.3.x series is an **experimental public beta candidate**, not a production-supported security release. Older artifacts are retained for reproducibility but are not maintained security branches. Do not send secrets, proprietary source, live exploit payloads, or private prompts in a public issue. Before public launch, the repository owner should enable GitHub's **private vulnerability reporting** and review incoming advisories; no private reporting channel has been configured by this ZIP. If private reporting is not yet enabled, request a private contact channel without posting exploit details.

Run `python tools/prepare_github.py --json` before staging a public snapshot and inspect the actual staged diff and Git history. The scanner catches some credential formats and risky filenames, including text under `validation/`; it cannot certify that screenshots, logs, notebooks, or dependencies are safe to publish. This ZIP does not grant untrusted users an agent execution service, nor provide an independently validated sandbox.

## v1.2.9 — local API request processing

Authenticated `/api/` POST, PUT and PATCH bodies are capped at 2 MiB before JSON parsing; requests bearing an invalid or absent API bearer token are rejected before parsing the body. Requests with an oversized declared Content-Length or oversized streamed body receive HTTP 413. This is only a per-request application-layer limit: it is **not** a substitute for a trusted reverse proxy, read/header timeouts, per-IP resource quotas, firewall, or isolation. GitHub webhooks retain their independent MAX_BODY policy. These changes are tested with local FastAPI TestClient; no adversarial network penetration testing was performed.

**Release warning:** A successful Windows local test report cannot certify security boundaries for hostile workloads. Windows EXE signing, native macOS/Linux packaging, provider authentication, hostile multi-tenant isolation and independent exploit testing are NOT VERIFIED for this release.

## v1.0.0 security update
See [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md) for signed audit, optional vault, reference guest and remaining risks. **Untrusted multi-tenant agent execution remains disabled.**

# Security policy

This is an experimental single-operator local tool. Do not expose its API publicly, run it as administrator/root, or give untrusted users access to its database, token or adapter configuration. Do not submit secrets in prompts. Use dedicated workspaces and least privilege. Codex authentication is managed separately; no bundled keys. Custom adapters execute in-process and must be trusted. The timeout argument is a contract for custom adapters, not a runtime-enforced sandbox. A timeout or worker crash can leave external work running. Lease fencing guards the database, not external effects. No encryption-at-rest is provided. The default local API has no tenant isolation; the restricted v0.7.0 API pilot is described below. Do not enable automatic retries unless inputs and external actions are replay-safe.

Before public release, the maintainer should enable private vulnerability reporting on GitHub and publish a supported-version policy. Do not publish exploit details or credentials in public issues.

## Recovery and backups

An expired lease or Codex error may indicate partial external effects. Verify that the old process has stopped and inspect its workspace and outputs before approving any replay. Store operator reasons and backups securely; they can contain sensitive data. Backups are not encrypted by AgentFlow. The audit log is not tamper-proof.

## Cancellation and restore (0.5.0)

Cancellation does not roll back effects. Linux subreaper cleanup handles ordinary detached descendants, not hostile processes or external services. On Windows 11 Pro x64, validation observed ordinary child and grandchild exits after cancellation, timeout and normal leader exit. Job Objects manage process lifetime for these trusted fixtures. Other POSIX cleanup is best effort. Restore only trusted backups with all original workers stopped. Restored queued jobs are held for explicit audited review before replay; never run original and restored queues simultaneously. Never expose the single-operator API publicly.

## Plugins and local models

Only load explicitly trusted Python plugins. They execute with worker/server privileges, and their capabilities are declarations, not a sandbox. The SDK is a trusted local interface. All non-echo API/CLI jobs require approval; only echo is automatically retried. Ollama is loopback-only, but the operator controls which service and model is actually running. Never publish prompts, results or real tokens in validation artifacts.

### v0.6.0 additions

External CLI adapters are opt-in and execute trusted binaries with host authority. Claude plan mode and no built-in tools do not disable all local hooks or external configuration. OpenCode uses standalone mode without auto-approval, not an enforced security sandbox; prompts are visible in argv. Never send secrets or expose the API to untrusted users. On Windows the new adapters reject .bat/.cmd shell wrappers. Optional delegated Linux cgroups improve descendant cleanup if the supervisor fails, but are not a privilege boundary or a guarantee against worker crashes. No credentials or API keys are packaged. Worker heartbeats are best-effort telemetry only; leases remain authoritative. Old schema v2 binaries must not open a v3 database; back up before upgrade.

## v0.7.0 trust boundaries

The new [restricted API pilot](TENANT_MODE.md) separates tenant DBs and enforces a role policy. It cannot run external adapters or plugins, intentionally. It is not a production security boundary for hostile workloads. Do not mix tenant queues with regular external agents. The original single-operator CLI/API trust boundary is unchanged. Use a private data directory and high-entropy tokens, keep raw credentials out of logs, and protect prompts, results and backups.

GitHub integration verifies raw-payload HMAC, repository allowlists, event types, payload size and replay identifiers. It never writes to GitHub. Issue and PR text are untrusted and must not be treated as instructions. Approval does not neutralize prompt injection or revoke an external CLI's permissions. Keep external agents disabled unless trusted and separately isolated. Expose only the webhook through a constrained TLS relay if necessary. See [GitHub integration](GITHUB_INTEGRATION.md).

Schema v4 holds restored active workflows and preserves existing queue restore protections. A failed branch stops new stages, not already-started independent branches. Do not replay restored workflows without inspecting external effects. No authenticated provider, native Windows, delegated cgroup, external penetration test or live GitHub delivery is claimed by this release.

## v0.8.0: PostgreSQL and Docker sandbox trust boundary

- **PostgreSQL** protects database state transitions across hosts using a transaction-level advisory lock, unique idempotency keys and lease fencing. It cannot roll back shell commands, external APIs or writes already made by a coding agent. Do not claim exactly-once execution of external effects. Database credentials must be rotated and restricted, and backup/restore procedures must be independently tested.
- **DockerSandboxAdapter** is strictly opt-in and refuses mutable/unpinned images; every task has a new container, no network, no mounts, a read-only filesystem, no privileges or host Docker socket, and resource/time/output limits. This is defense-in-depth for trusted operators, **not** a security certificate for hostile multi-tenancy. The Docker daemon has high host privileges; never share its socket with untrusted workloads or exposed API services. A crash between Docker launch and cleanup may leave an orphan container. For truly hostile code, require disposable independent VMs/microVMs, validated isolation, and separate brokered secrets.
- Restricted tenant mode continues to block external agents, plugins and Docker sandbox jobs; adding PostgreSQL is **not** an authorization to relax that rule.
- Distributed workers require time synchronization; a lease can expire during network partitions and leave external side effects uncertain. Verify both the workload and its environmental effects before replaying.
- The Compose example is loopback-bound, uses an internal network, does not expose PostgreSQL, and does not mount Docker socket. It is not hardened or tested as a public Internet service. See [DEPLOYMENT.md](DEPLOYMENT.md).
- PostgreSQL live integration, Linux Docker isolation, Windows host isolation, negative penetration tests and authenticated coding-agent sessions remain unverified in the authoring environment until explicitly tested on a suitable host.


## v0.9.0 additions — important non-guarantees

- SQLite schema v5 and PostgreSQL schema v2 record database-scoped rate counters and actor/action audit records. The audit contains no raw token or prompt by design. It is **not append-only/tamper-proof**, and a crash can occur between a completed operation and a separate audit transaction.
- API rate limiting is fixed-window and keyed by hashed bearer identity; it does **not** stop credential sharing or supply a production identity provider. In restricted tenant mode, non-admin accounts cannot read the audit API. For public-facing use add a reverse proxy, per-IP quota, TLS, credential rotation and dedicated operations review.
- `ScopedSecrets` and `EgressPolicy` are opt-in helper APIs for trusted integrations. They **do not contain** arbitrary agent traffic or enforce a secret vault. DNS-pinned HTTPS forbids redirects and nonpublic IPs in the broker, not in an external agent process.
- QEMU `QemuVMAdapter` is opt-in, requires pinned audited guest image, no network or mounted host files, and uses snapshot-mode disk. No guest OS is shipped and no native QEMU/hostile attack verification has been performed. VM escape, host-kernel side channels, malicious guest images and insecure hypervisor configurations remain risks; use dedicated disposable machines for hostile workloads.
- The PostgreSQL pool and advisory transaction lock preserve database atomicity, not external-effect exactly-once execution. Network partition can leave a worker running after its lease expires. Retrying is **never** automatic for uncertain external effects.
- Do not grant the tenant API permission to run external agents solely because VM support exists. This gate remains intentionally closed pending an independent threat review and live adversarial testing.
