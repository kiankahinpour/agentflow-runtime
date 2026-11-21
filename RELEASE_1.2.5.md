# AgentFlow Runtime v1.2.5

## Change
The regression guard now streams subprocess output into a bounded 12 KiB in-memory tail instead of a potentially unbounded temporary file. A daemon reader drains the pipe while tests execute to prevent backpressure deadlocks. The guard reports total output bytes and truncation.

## Limits
A detached descendant inheriting the stdout pipe can outlive the test; the reader is daemonized and joined for one second only. Native Windows/macOS CI, Docker/PostgreSQL, QEMU, and standalone binary builds are not verified by this change. No provider API calls are made.
