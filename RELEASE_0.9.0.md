# AgentFlow Runtime 0.9.0 — Validation and handoff

This is an experimental release, **not** a security certification.

## Implemented features

- SQLite and PostgreSQL: atomic per-actor fixed-minute rate limit, actor audit and Prometheus text metrics.
- PostgreSQL: optional psycopg_pool connection pooling (`pip install -e ".[server,test,postgres-pool]"`).
- Workflow: dependency output substitution with bounded payloads and no recursive template evaluation.
- Trusted operator: explicit environment secret allowlist and DNS-pinned HTTPS egress allowlist.
- VM: experimental QEMU adapter using checksum-verified guest images, no guest network, bounded output and cancellation. Guest OS/protocol must be supplied and audited by the operator.
- Fault and soak: SIGKILL test, opt-in disposable Docker network disconnect, synthetic multi-process soak, native Windows smoke utility.
- GitHub: manual publication preflight only; no automatic publication.

## Required real-host checks (NOT VERIFIED here)

1. On a disposable PostgreSQL 17 database set `AGENTFLOW_TEST_POSTGRES_DSN` and run `python -m pytest tests/test_v080_pg_integration.py tests/test_v090_pg_integration.py -v`.
2. Run the opt-in Docker CI workflow on a dedicated host and verify network, read-only filesystem, process tree cleanup and resource enforcement.
3. Use a disposable audited QEMU guest image with the documented serial protocol; the fake QEMU test is a contract test only.
4. On Windows run `Validate_Windows.bat` and `python tools/windows_native_smoke.py` with a suitable host.
5. On a dedicated test host run `python tools/soak.py --seconds 7200 --workers 4 --rate 10`; record real throughput, CPU, memory, failure recovery and errors.
6. Run `python tools/prepare_github.py` and publish manually only after reviewing credentials, licensing, security and project ownership.

## Limitations

Rate limiting is fixed-window, not a global DDoS shield. PostgreSQL coordination uses a database-wide advisory transaction lock and is not a guarantee of exactly-once external effects. QEMU guest integrity and OS hardening are not proven by SHA-256 alone. The audit log is database-editable, not tamper-evident. Egress controls apply only when the scoped broker is used; they do not sandbox arbitrary adapters. Do not expose untrusted agent execution in multi-tenant mode.
