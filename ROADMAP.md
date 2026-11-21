## v1.3.1 — GitHub launch readiness (2026-11-21)

- [x] Extend offline pre-publication scanning to historical validation text, nested credentials, secret patterns and symlinks; strengthen git/docker ignore rules.
- [x] Fix source-checkout desktop smoke subprocess import failures; add targeted regression coverage.
- [x] Gate CI and manual artifact builds on a preflight scan; avoid automatic pull-request Docker fault injection.
- [x] Add a truthful operator-run publication checklist, explicit security reporting limitations and English release notes.
- [ ] Owner to review IP rights, historical screenshots/logs and staged Git diff before first public push.
- [ ] Execute the v1.3.1 CI matrix on actual GitHub-hosted Windows/macOS/Linux runners; no result is asserted before upload.
- [ ] Validate native EXE/APP/AppImage on corresponding hosts, then PostgreSQL/Docker fault injection, pinned QEMU boot and long soak.
- [ ] Independently review process isolation, local permissions, API attack surface, DNS/TLS and audit/secret safety before hostile workloads.

## v1.3.0 — HTTPS egress parsing hardening (2026-11-21)

- [x] Reject malformed DNS allowlist labels and unsafe raw HTTPS request-target bytes before DNS resolution.
- [x] Add offline regression tests for rejected and accepted targets.
- [ ] Validate on actual Windows/macOS hosts and hosted CI.
- [ ] Independently audit DNS pinning, TLS behavior, redirect rejection, and remaining SSRF vectors.
- [ ] Run real Docker/PostgreSQL failure tests and pinned QEMU boot on disposable infrastructure.

## v1.2.9 — pre-publication gates (2026-11-21)

- [x] Start from the corrected v1.2.8 Windows-validated source ZIP, not an earlier archive.
- [x] Gate unauthorized API POST body parsing; enforce bounded, streamed request bodies for authenticated API writes.
- [x] Fix distribution workflow version check for dynamic setuptools metadata; disable PyPI publishing entirely.
- [x] Update README and release evidence to distinguish reported Windows validation from local results.
- [ ] Get v1.2.9 CI results from **real** Windows, macOS, Linux runners; verify native Windows process tree coverage.
- [ ] Independently reproduce x64 EXE, macOS APP, and Linux AppImage on their respective hosts; review signing/distribution trust.
- [ ] Run disposable PostgreSQL + Docker fault-injection and partition tests; boot pinned QEMU guest.
- [ ] Security review: preauthentication request handling, local secret/key directory permissions, OpenCode argv exposure, rate limits and audit evidence.
- [ ] Obtain operator authorization before GitHub/PyPI publishing or live paid provider testing.

## v1.2.8 — bounded fail-fast diagnosis

Windows regression coverage now includes observed child and grandchild exits, a native guard timeout, a browser driven against a loopback API, and rollback after a killed SQLite writer. Keep these checks in the Windows matrix. Separate gates remain for Docker and PostgreSQL lifecycle tests, a pinned QEMU guest, and repeated native builds on independently configured Windows hosts.

- [x] Add opt-in fail-fast with durable incomplete report and a regression test.
- [ ] Complete module-by-module regression with realistic timeouts (the process cleanup tests include multiple deliberate waits).
- [ ] Collect hosted Windows/macOS/Linux CI evidence and native binary build logs.
- [ ] Validate Docker/PostgreSQL fault injection and pinned QEMU boot on disposable hosts.

