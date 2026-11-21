# AgentFlow Runtime v1.3.1 — local validation evidence (2026-11-21)

**Source base:** `AgentFlow_Runtime_v1.3.0_Security_Hardening.zip`, not any older version. 
**Host:** Linux 6.18.57 x86_64, Python 3.13.5, pytest 9.0.2, FastAPI 0.128.2, HTTPX 0.28.1. The environment is a Linux container, **not** GitHub Actions or a native Windows/macOS host.

| Check | Actual result |
|---|---|
| Baseline `python -m pytest -q --disable-warnings` from v1.3.0 source without `PYTHONPATH` | 184 passed, 14 skipped, **1 failed** (desktop child service could not import the checkout); reproduced with an isolated test |
| Baseline isolated desktop smoke after `PYTHONPATH=src` workaround | 1 passed; supported import-path diagnosis |
| v1.3.1 targeted regression, API and URL hardening | **38 passed in 2.40s** (tests/test_github_publication_preflight.py, tests/test_public_beta_gates.py, tests/test_egress_url_hardening.py) |
| v1.3.1 complete `python -m pytest -q -ra` without manually setting `PYTHONPATH` | **201 passed, 14 skipped, 0 failed in 73.24s**; `validation/v1.3.1/linux-pytest-final.log` |
| `python tools/prepare_github.py --json` | PASS; see limitations below |
| `python tools/check_release_version.py --version 1.3.1` | PASS |
| `python -m compileall -q src tools tests` | PASS |
| `python -m pip wheel . --no-deps --no-build-isolation` | Built `agentflow_durable-1.3.1-py3-none-any.whl` in an isolated output directory |
| Install resulting wheel to an independent target and inspect import/package version | PASS, 1.3.1 from wheel target outside repository |
| Parsing of ten `.github/workflows/*.yml` files with PyYAML | PASS (syntax parse only, **not** GitHub Actions execution or actionlint) |

**Fourteen full-suite skips:** nine Windows Job Object/process-handle cases, one delegated Linux cgroup case, and four PostgreSQL cases requiring live disposable services. Skips are not successes; see the full log for exact test identifiers.

**What was actually changed and tested:** The new preflight and expanded ignore rules check/protect nested files, common secret patterns (including historical logs), local credential-looking filenames, symlinks and explicit publishing markers; it does not print detected secret values. Desktop source-mode child processes receive the checkout's `src/` import path when absent from the environment. New regression tests cover these cases. The PostgreSQL fault-injection workflow now runs only by explicit dispatch.

**NOT VERIFIED:** CI on actual GitHub-hosted Windows/macOS/Linux, Windows EXE/native Windows process handles for v1.3.1, macOS APP, Linux AppImage, live PostgreSQL or Docker fault injection, real QEMU guest boot, paid/live model providers, long soak, publisher signature, exhaustive secrets detection, independent security audit, public Internet exposure, or hostile multi-tenant isolation.

**Publication:** Nothing was pushed to GitHub or PyPI. The source should be reviewed by its rights holder and scanned externally before a public push. SHA-256 proves file integrity relative to the manifest, not publisher identity.
