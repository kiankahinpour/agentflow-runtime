# AgentFlow Runtime 1.2.4

## Changes
The isolated regression runner no longer buffers unlimited child process output in memory. It uses a temporary disk file, retains the final 12 KiB, and records `output_bytes` and `output_truncated` in JSON. Temporary logs are removed after each module.

## Evidence
`python -m pytest -q tests/test_regression_guard.py`: 5 passed (Linux). A full suite attempt was not completed; no full-suite pass is claimed. The environment has no Docker binary and native Windows/macOS CI and QEMU boot were not run.

## Limitations
Temporary logs can still consume disk space while tests run. This is not a disk quota or sandbox. Never execute untrusted test modules on a shared machine.
