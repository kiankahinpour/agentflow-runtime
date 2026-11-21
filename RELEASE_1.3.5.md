# AgentFlow Runtime v1.3.5 — CI checkout evidence and heartbeat test reliability

**Release status:** Source-only public-beta candidate. No GitHub push, tag, PyPI upload, live coding-agent call, or paid API operation was carried out when preparing this package.

## Base and observed failure

This change was made on the complete `AgentFlow_Runtime_v1.3.4_CI_Mac_Windows_Fixes.zip` archive, not on a stale earlier branch.

The owner supplied GitHub Actions log exports for commits `5eb57d2` and `2c8d34b` on 2026-11-21. The `2c8d34b` checkout of the public repo still runs the pre-v1.3.4 version of `src/agentflow_runtime/adapters.py` (`os.killpg(..., signal.SIGKILL)` in the original POSIX cleanup block). Its pytest output also lacks the new v1.3.4 regression tests. Consequently, a commit caption that mentions v1.3.4 is **not evidence** that the fixed source files were included in the commit. The submitted logs cannot prove why the upload differed from the requested source tree.

From the most recent archive, the nine Python test matrix outcomes are:

| Runner | Result captured in supplied logs |
|---|---|
| Ubuntu, Python 3.10 / 3.12 / 3.13 | 201 passed, 14 skipped on each runner |
| macOS, Python 3.10 / 3.12 / 3.13 | 1 failed, 188 passed, 26 skipped on each runner (POSIX `PermissionError`) |
| Windows, Python 3.10 / 3.12 | 1 failed, 188 passed, 26 skipped on each runner (Windows path diagnostic) |
| Windows, Python 3.13 | 2 failed, 187 passed, 26 skipped (path diagnostic plus `test_heartbeat`) |

These are **results of the repository revision in the logs, not v1.3.5 results**. The `StarletteDeprecationWarning` seen in these logs is not the cause of these particular failures.

## Code changes

1. Add `tools/ci_source_guard.py`, a non-network source checkout check for the expected package version and for markers identifying the v1.3.4 macOS and Windows fixes and regression tests. This intentionally fails before pytest if the updated CI workflow is present but critical source changes were not copied.
2. Require `python tools/ci_source_guard.py --expected-version 1.3.5` after dependency installation and before pytest in `.github/workflows/ci.yml`. **Update this expected version whenever changing the project version.** A stale workflow that was never copied cannot run this guard; therefore visually inspect the remote commit, too.
3. Replace the timing-sensitive 300 ms lease / 550 ms sleep in `test_heartbeat` with an observed successful renewal event and a five-second synthetic lease. This still tests real worker renewal and successful completion, without treating scheduling stalls as runtime bugs. Expired-lease fencing and real worker code are unchanged.
4. Add `tests/test_ci_source_guard.py` with positive, stale-version, missing-file, and workflow-order checks.

## Local validation

- On the preparation host (Linux): `python -m pytest -q -ra`: **217 passed, 14 skipped**, no failures, in **73.61 seconds**.
- Focused `tests/test_ci_source_guard.py`, `tests/test_core.py`, `tests/test_adapters.py`, `tests/test_github_publication_preflight.py`: **42 passed** (prior to documentation edits).
- These local results do not establish Windows/macOS compatibility, VM or Docker isolation, live provider compatibility, or production readiness.

## Release and GitHub Desktop procedure

1. Extract the **full** `AgentFlow_Runtime_v1.3.5_CI_Source_Integrity.zip`. If it contains a parent `agentflow-runtime` directory, open that directory and copy its **contents**, not the directory itself, into the directory opened by **GitHub Desktop > Repository > Show in Explorer**.
2. Keep the existing `.git` directory intact. In GitHub Desktop, review the Changes list. It should include changes to both `src/agentflow_runtime/adapters.py`, `tools/prepare_github.py` (relative to the *published* v1.3.2 code), the new `tools/ci_source_guard.py`, `.github/workflows/ci.yml`, `tests/test_core.py`, and `src/agentflow_runtime/_version.py`.
3. From the repository root, run `python tools/ci_source_guard.py --expected-version 1.3.5`, `python tools/prepare_github.py --json`, and (after staging files) `python tools/prepare_github.py --staged --json`. Inspect `git diff --cached --stat` and `git diff --cached` for sensitive data or missing files.
4. After owner review, commit and push. The **GitHub website** should display `__version__ = "1.3.5"` in `src/agentflow_runtime/_version.py` and `def _stop_posix_group(` in `src/agentflow_runtime/adapters.py` at that exact commit.
5. On GitHub Actions, read the **new commit SHA** and confirm that the **Verify CI checkout version and cross-platform fixes** step is present and passes. Then collect outcomes for all nine pytest matrix jobs.

## Explicit limitations

- This is not a cryptographically signed or authenticated source provenance system. String marker checks cannot guarantee complete code integrity or safe process-tree containment.
- The v1.3.4 macOS fix still requires **native macOS validation of descendant cleanup**. Its fallback protects the leader but does not attest that all detached or permission-protected descendants were terminated.
- Windows XP/other releases, macOS, Linux distributions beyond the preparation host, Windows EXE, macOS APP, AppImage, real PostgreSQL/Docker fault injection, QEMU guest boot, secrets/audit independent review, and paid model integrations remain unverified for **v1.3.5**.
- The 300 ms heartbeat failure in the supplied Windows Python 3.13 logs is not independently attributed to a production worker defect; this release removes a brittle unit-test timing assumption, not durable lease fencing.
