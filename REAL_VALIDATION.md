# Native and integration validation matrix — v1.1.0

**A script or workflow existing is not evidence that it ran.** All unavailable tests must be labeled `UNVERIFIED` in release notes. Review logs and linked CI run identifiers before claiming a pass.

| Test | How to run | Prerequisites | Current local status |
|---|---|---|---|
| Linux Python regression | `python -m pytest -q` | Python / test extras | Run locally; see RELEASE_TESTS.md |
| Windows/macOS native API and Job Objects | `.github/workflows/ci.yml` | GitHub hosted OS runners | UNVERIFIED |
| Native EXE / `.app` / Linux onedir | `.github/workflows/native-builds.yml` | PyInstaller on each runner | UNVERIFIED |
| AppImage | `tools/build_native.py --appimagetool PATH` | Audited `appimagetool` executable | UNVERIFIED |
| PostgreSQL distributed state | `.github/workflows/postgres-integration.yml` | PostgreSQL 17 CI service | UNVERIFIED |
| Docker PostgreSQL kill/restart/network partition | `.github/workflows/postgres-fault-lab.yml` | Disposable Docker containers | UNVERIFIED |
| Docker process sandbox | `.github/workflows/docker-sandbox.yml` | Docker daemon | UNVERIFIED |
| Reference QEMU guest boot | `.github/workflows/qemu-guest-lab.yml` | Operator-pinned Debian image + SHA256, QEMU | UNVERIFIED |
| 1–2 hour synthetic worker crash soak | `.github/workflows/chaos-soak.yml` | Explicit manual dispatch | UNVERIFIED |
| Codex/Claude Code/OpenCode real calls | `python tools/provider_matrix.py --allow-live-calls --accept-provider-costs` | CLI + authenticated account, operator permission | UNVERIFIED |

## GitHub repository actions

GitHub repositories and PyPI projects are **not created or published automatically**. Run `python tools/prepare_github.py`, review `SECURITY.md`, the license and contribution rules, and manually create a public repo. The release workflow now **defaults to build-only**; PyPI upload requires explicit manual `publish_pypi=true` and a protected `pypi` environment.

## Security conditions before untrusted multi-tenant execution

Do not enable hostile code in the multi-tenant API. VM snapshots, QEMU serial protocol, cgroup limits, Docker isolation, encrypted secrets and signature chains are useful controls but not an independently audited security boundary. Require operator-controlled microVM/VM infrastructure, network egress policy, host credential isolation, hardened images, threat modeling, patch management, and external penetration review. Never expose Docker socket or bearer tokens to untrusted workloads.
