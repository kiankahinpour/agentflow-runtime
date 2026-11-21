# AgentFlow Runtime v1.0.0 — release candidate (NOT certified)

Date: 2026-11-21. Built from v0.9.0 source. **Do not describe as production-ready until independent platform and security verification.**

## Implemented
- Three local startup scripts (`Start_AgentFlow_Windows.bat`, `Start_AgentFlow_Linux.sh`, `Start_AgentFlow_macOS.command`) using venv, localhost API and Echo/Word Count worker. No external API calls or hosted credentials used.
- `tools/doctor.py` and `tools/start_local.py` read-only preflight / launcher; CI matrix for Windows, Ubuntu/Linux, macOS and Python 3.10/3.12/3.13; native HTTP launcher smoke.
- HMAC-SHA256 append chain for new audit events; independent checkpoint validation, visibility of unsigned legacy rows, multi-tenant admin-only audit verification.
- Optional Fernet local vault with external master key, name allowlist and atomic file writes. This is not an OS keychain.
- Reference QEMU guest Python agent, systemd service, build recipe from a trusted cloud disk image, and host-side READY handshake before prompt transmission.
- PostgreSQL schema v3 and SQLite schema v6 migrations, live integration tests gated behind `AGENTFLOW_TEST_POSTGRES_DSN`.
- New tests, docs, security threat model, publication guidance and reproducible local scenarios.

## Verified in this environment
- Linux / Python 3.13.5 full unit+integration suite: 115 passed, 6 skipped (source tree, final run 56.73s).
- Portable launcher direct HTTP loopback → enqueue Echo → worker success (Linux).
- Real Chromium 1440px/1024px/390px browser interface via offline TestClient bridge; direct browser network to local server not verified by browser smoke.
- 20 second, 240 Echo jobs, 4 independent worker processes, zero duplicate claims, SQLite `integrity_check=ok`.
- 5 second, 50 jobs / 2 workers clean.
- Linux process tree fixture (3 scenarios) passed when executed separately.
- A 60-second soak attempt was interrupted by the execution environment before producing a final result and is NOT counted as passed.
- Provider CLIs, real PostgreSQL, Docker, QEMU, Windows/macOS runners unavailable locally, so no live validation claim.

## Unverified / blocked
- Windows Job Objects on real Windows, macOS process group native tests, PostgreSQL pooled transactions on live host, Docker isolation, actual guest VM boot/isolation, 2 hour soak with worker crash + network partition, and authenticated Codex/Claude/OpenCode.
- Public GitHub/PyPI publication and external user adoption (manual steps only).
- HMAC chain only detects authenticated-row manipulation while secret remains unknown, and suffix deletion only when externally anchored; no immutable audit ledger guarantee.

## Exact commands for operators

```bash
python tools/doctor.py --json
python tools/run_platform_validation.py --with-native
python tools/launcher_smoke.py
python -m pytest -q
python tools/soak.py --seconds 7200 --workers 4 --rate 10
python tools/live_provider_smoke.py codex --allow-live-call # may use quota
python tools/qemu_guest_smoke.py --image guest.qcow2 --sha256 <SHA256> --allow-real-boot
```

Use a disposable test host for fault injection; see `OPERATIONS_090.md`, `CROSS_PLATFORM.md`, `SECURITY_ARCHITECTURE.md` and `COMMUNITY_LAUNCH.md`.
