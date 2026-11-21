> **Current release:** For v1.3.1 local test results see [RELEASE_TESTS_1.3.1.md](RELEASE_TESTS_1.3.1.md). The below material is historical evidence for v1.2.9 and earlier; do not count it as current cross-platform CI.

# AgentFlow Runtime 1.2.9 — independently run local validation (2026-11-21)

**Host:** Linux x86_64, Python 3.13.5, pytest 9.0.2, FastAPI 0.128.2, HTTPX 0.28.1. Current checks are local, not a hosted GitHub Actions matrix. No public publication or paid provider call was performed.

| Actual check | Result |
|---|---|
| `PYTHONPATH=src python -m pytest -q -ra` | **170 passed, 14 skipped, 0 failed in 73.58s**; see `validation/v1.2.9/linux-pytest-final.log` |
| Focused API, release and regression guard tests (`tests/test_api.py tests/test_public_beta_gates.py tests/test_release_verifier.py tests/test_regression_guard.py`) | **42 passed in 12.15s** |
| Updated `tests/test_v110.py` + beta gates tests | **17 passed in 3.92s** |
| `python tools/check_release_version.py --version 1.2.9` | PASS |
| Version mismatch guard `--version 1.2.8` | Correctly refused |
| `python -m pip wheel . --no-deps --no-build-isolation` | Built `agentflow_durable-1.2.9-py3-none-any.whl` locally |
| `python tools/prepare_github.py` | PASS for its **limited** file/pattern checks; **not** a full secret audit |
| `python -m compileall -q src tools tests` | PASS |
| YAML parse of release/CI/native workflows | PASS with installed PyYAML 6.0.3 |

**Fourteen skips:** nine Windows-native conditions, one delegated Linux cgroup condition and four PostgreSQL integration conditions. See the exact skip reasons in the final test log.

The initial full regression without proper subprocess `PYTHONPATH` did not complete; an intermediate restricted run recorded two failures (a subprocess import/environment issue and an obsolete release-policy test). The environment was configured correctly and the obsolete test updated to enforce the new stricter no-PyPI-publish policy. The **final** full run above is the authoritative local result.

**Not verified in this run:** Windows/macOS execution of v1.2.9, GitHub-hosted runners, EXE/APP/AppImage native builds, PostgreSQL/Docker fault injection, QEMU guest boot, live Codex/Claude Code/OpenCode authorization/execution, security penetration testing and independent publisher signing.

**Operator-provided prior Windows report:** Corrected v1.2.8 reportedly had 151 passed, 26 skipped, 0 failed tests and an unsigned Windows x64 EXE native smoke. The original Windows raw logs and the executable are not bundled here and were not independently reproduced. Do not combine this with the local v1.2.9 counts.

## Historical v1.1.0 validation

# v1.1.0 release candidate validation — 2026-11-21

**Environment:** Linux, Python 3.13.5. No real PostgreSQL/Docker/QEMU, macOS/Windows native host, PyInstaller, or authenticated AI provider was available in this execution environment.

| Check | Result |
|---|---|
| Full Python regression (`python -m pytest -q`) | **125 passed, 6 skipped**, 59.86s (final rerun after startup-race fix) |
| Desktop source-mode local end-to-end Echo/API (`python -m agentflow_runtime.desktop --self-test`) | PASSED |
| Installed wheel in independent target directory and ran local desktop self-test | PASSED |
| Synthetic SIGKILL chaos soak (4s / 2 workers / 20 Echo tasks) | 19 succeeded, 1 uncertain, 0 duplicate claims, SQLite integrity OK |
| QEMU protocol with long-lived fake guest and real kill-on-reply | PASSED; no real QEMU boot |
| Chromium browser, 1440/1024/390 px, offline FastAPI bridge | PASSED |
| Chromium direct HTTP `127.0.0.1` | BLOCKED by environment administrator; NOT PASSED |
| Cross-platform CI workflow definitions | Written; NOT EXECUTED on GitHub |
| Windows EXE / macOS APP / Linux AppImage binaries | Build tooling written; NOT BUILT locally (PyInstaller unavailable) |
| Docker PostgreSQL crash/network injection | Code and workflow written; NOT EXECUTED locally |
| Real QEMU Guest image boot | Code and opt-in workflow written; NOT EXECUTED |
| Live Codex, Claude Code, OpenCode | Unavailable; preflight confirms CLI binaries missing |
| Long-duration (1–2 hour) chaos and multi-host resilience | Code and manual CI workflow written; NOT EXECUTED |

Initial post-ZIP smoke showed one intermittent desktop startup failure; investigation found concurrent initialization of a fresh SQLite schema. **The launcher was corrected to start API first and Worker second.** Ten repeated source desktop self-tests and 21 selected tests then passed. The final artifact includes that fix.

`validation/v1.1.0/dashboard-*.png` contains Chromium screenshots from the local HTML/FastAPI TestClient bridge. No metric or status in this document should be interpreted as a hosted CI result or security certification.
