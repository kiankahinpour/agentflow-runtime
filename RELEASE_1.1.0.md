# AgentFlow Runtime v1.1.0 — validation and native release tooling

**Release candidate.** This project can run locally using its Python package on Linux (locally checked), with source launchers for Windows and macOS (native validation pending). It is not security-certified for hostile multi-tenancy.

## Changes

- Fixed intermittent first-run local SQLite initialization race by starting the API before the worker; 10 repeated self-tests passed.

- Hardened QEMU default READY handshake (legacy fake-guest test opts into preload mode explicitly). Fixed QEMU guest result handling: after a verified single serial reply, terminate the still-running VM rather than waiting until timeout.
- Added portable source/frozen `agentflow-desktop` entrypoint with local-only API + Echo worker and an actual self-test that submits a task and verifies the result.
- Added native PyInstaller packaging tool: draft Windows EXE, macOS APP, Linux onedir and optional AppImage with audited appimagetool.
- Added manual `native-builds.yml` for Windows/Linux/macOS binary generation and self-tests.
- Added opt-in disposable Docker PostgreSQL crash and network-partition test and explicit CI job.
- Added multi-process SIGKILL chaos soak with lease reconciliation and audit of duplicate claims.
- Added optional pinned-image QEMU boot workflow (requires operator-managed image SHA256).
- Added provider preflight and opt-in smoke harness. No API credits consumed in default tests.
- Made manual PyPI release workflow build-only by default, requiring additional explicit publish approval.
- Added public release documentation and a per-platform verification matrix.

## Non-claims

This artifact does **not** claim success on GitHub-hosted Windows/macOS runners, real PostgreSQL/Docker, real QEMU guest, real model accounts or an actual AppImage build without an audited tool. Community adoption and acceptance to OpenAI's Codex for Open Source are unverified. No repository was published.
