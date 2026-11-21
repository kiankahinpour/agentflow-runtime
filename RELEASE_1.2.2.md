# AgentFlow Runtime v1.2.2

This release adds `tools/regression_guard.py` to diagnose tests that hang or leave child processes behind. Run `python tools/regression_guard.py --timeout 90 --report regression-report.json`. Each test module runs in its own subprocess; a timeout is reported as a failure. The runner is diagnostic, not a substitute for real cross-platform CI. Do not run untrusted test modules on a privileged machine.

Native Windows/macOS CI, PostgreSQL/Docker fault injection, QEMU guest boot, and agent-provider authentication remain unverified. No public release or API calls were made.
