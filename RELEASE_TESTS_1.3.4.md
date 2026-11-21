# v1.3.4 local validation record (2026-11-21)

**Environment:** Linux x86_64, Python 3.13.5. This is not a native macOS/Windows run.

| Verification performed locally | Observed result |
|---|---|
| `PYTHONPATH=src python -m pytest -q tests/test_adapters.py tests/test_github_publication_preflight.py tests/test_ci_matrix_resilience.py` | **31 passed** in 7.23s |
| `PYTHONPATH=src python -m pytest -q tests/test_regression_guard.py` | **11 passed** in 11.74s |
| `PYTHONPATH=src python -m pytest -v -ra` | **212 passed, 14 skipped, 0 failed** in 74.10s |
| `PYTHONPATH=src python tools/prepare_github.py --json` | **PASS**, file-name/credential-pattern scan only |
| `PYTHONPATH=src python tools/check_release_version.py --version 1.3.4` | **PASS** |

The full suite was retried with verbose output after a bounded intermediate run stalled in subprocess-heavy regression tests. The final complete run passed. `14 skipped` represents host- or environment-gated tests; **not** a pass for live PostgreSQL or Windows process-tree integration.

The uploaded hosted GitHub Actions logs for the prior v1.3.2 commit are summarized in `RELEASE_1.3.4.md`. Updated v1.3.4 CI on real Windows and macOS runners is **NOT VERIFIED**. QEMU VM boot, sustained stress, live paid model invocation, independent security audit, native binary signing and release are **NOT VERIFIED**.
