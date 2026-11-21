# AgentFlow Runtime 1.2.7

## Changes

Regression Guard now checkpoints `running_module` before each test module starts. An interrupted run leaves `complete: false` and the active module name in its JSON report. Child pytest stdin is disconnected from the controlling terminal to prevent accidental interactive blocking.

## Validation

- `python -m pytest -q tests/test_regression_guard.py`: 10 passed (Linux).
- `python -m pytest -q tests/test_adapters.py tests/test_cancellation_restore.py`: 19 passed (Linux).
- Full regression: incomplete (no all-pass claim).
- Native Windows/macOS CI, binaries, real Docker/PostgreSQL and QEMU guest: NOT VERIFIED.

## Limitations

An in-flight module record is diagnostic only; it does not prove a defect in that module. No release signatures or public publishing were performed.
