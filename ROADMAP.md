## v1.3.5 — verify the *deployed* checkout before native CI (2026-11-21)

- [x] Start from the complete v1.3.4 ZIP and inspect the latest uploaded nine-job GitHub Actions logs, including Windows Python 3.13 heartbeat failure.
- [x] Add version/fix marker validation to CI to detect partial source uploads before pytest.
- [x] Replace short scheduler-dependent heartbeat timing with observed lease renewal and add regression coverage.
- [x] Run local Linux full regression with source candidate: 217 passed, 14 skipped.
- [ ] **P0:** owner must copy the full **contents** of the updated archive to the actual GitHub Desktop repository root, review staged files, and verify the changed source files on GitHub after Push. Do not infer completeness from the commit title.
- [ ] **P0:** run all 9 GitHub-hosted Windows/macOS/Ubuntu Python jobs for the new SHA; record checkout guard result and any remaining native failures.
- [ ] **P1:** instrument real macOS descendant process cleanup; `EPERM` is an uncertainty, not an isolation guarantee.
- [ ] **P1:** reproduce and characterize 300 ms lease heartbeat under Windows load separately from the stable unit test.
- [ ] **P2:** native package builds, disposable PostgreSQL/Docker fault injection, pinned QEMU guest, long soak, independent Secrets/Audit review.

## v1.3.4 — observed hosted matrix failure remediation (2026-11-21)

- [x] Use the newest available source ZIP (v1.3.3) and inspect the actual uploaded nine-job GitHub Actions logs.
- [x] Fix macOS process-group `EPERM` handling without treating uncertain descendant cleanup as verified containment.
- [x] Make repository publication-check diagnostic paths OS-neutral to avoid Windows-only regex failures.
- [x] Add regression cases and preserve all existing test coverage.
- [ ] **Highest priority:** push this source candidate only after owner review, and obtain new green results for all nine hosted Windows/macOS/Linux Python jobs.
- [ ] Investigate whether a denied process-group signal leaves descendants running on real macOS; run an instrumented non-privileged process-tree test and document limits before claiming cancellation containment.
- [ ] Validate native EXE/APP/AppImage on corresponding hosts; run PostgreSQL/Docker lifecycle faults, a pinned QEMU guest and extended soak tests under explicit resource budgets.
- [ ] Address Starlette/httpx deprecation warning by testing a supported dependency upgrade; avoid unreviewed major-version changes.
- [ ] Review release source, CI logs, secrets, permissions and Git history; do not claim the source candidate is production safe.

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

