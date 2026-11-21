# AgentFlow Runtime 1.2.3 — regression timeout diagnostics

This release improves `tools/regression_guard.py` with verbose test-case identification and a best-effort pytest faulthandler timeout setting before the hard wall-clock kill. The Windows process-tree termination fallback now tolerates `taskkill` errors/timeouts and kills the parent process if still alive.

## Validation
- `python -m pytest -q tests/test_regression_guard.py`: 4 passed on Linux.
- Full-suite execution was attempted but did not complete within the execution window. No full-suite success claim is made.
- Windows cleanup behavior, macOS, PostgreSQL/Docker, QEMU and native builds remain unverified.

## Diagnostic limitation
The faulthandler traceback is best effort; plugins and process termination may prevent it from appearing. Verbose pytest output identifies the running test in captured reports.
