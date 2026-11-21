# AgentFlow Runtime 1.2.8

This maintenance release introduces `--fail-fast` in `tools/regression_guard.py`. When enabled, the runner stops at the first failed or timed-out module, records that module in the JSON results, and leaves `complete=false` to avoid representing an aborted run as a full regression.

Usage: `python tools/regression_guard.py --timeout 90 --fail-fast --report regression.json`

A diagnostic run with a deliberately short 18-second timeout timed out on `test_cancellation_restore.py` during its process cleanup fixtures; these tests intentionally wait several seconds each. This observation does not prove a product deadlock. Native Windows/macOS CI, PostgreSQL/Docker fault injection, QEMU boot, and native packaging are not verified. No public publication or paid provider API execution occurred.
