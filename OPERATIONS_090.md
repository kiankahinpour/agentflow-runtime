# AgentFlow v0.9.0 — operator validation and release handoff

## Feature status matrix

| # | Feature | Implemented code | Local verification | Native validation needed |
|---|---|---|---|---|
| 1 | PostgreSQL + Docker CI | `.github/workflows/postgres-integration.yml`, `docker-sandbox.yml` | Test configuration and contracts | Execute GitHub-hosted CI against real PG/Docker |
| 2 | Worker crash + DB network partition | `tools/fault_worker_smoke.py`, `tools/network_fault_smoke.py` | Real local subprocess SIGKILL and lease fencing | Run PG partition on disposable Docker network |
| 3 | VM / microVM stronger isolation option | `src/agentflow_runtime/vm.py`, CLI `--vm-image` | Fake-QEMU protocol, argument and digest tests | Boot audited QEMU guest; hostile validation |
| 4 | Scoped secrets + network broker | `src/agentflow_runtime/secrets_policy.py` | Allowlist/SSRF-deny unit tests | TLS egress integration, deployment-specific policy |
| 5 | PostgreSQL connection pooling | `src/agentflow_runtime/postgres.py`, `AGENTFLOW_PG_POOL_SIZE` | Pool contract via mock | Real psycopg_pool on PG CI |
| 6 | Workflow result handoff | `src/agentflow_runtime/workflows.py` | Multiple workflow tests | Review prompt-injection risks and external agents |
| 7 | Rate limiting + identity audit | `Store.rate_limit`, `Store.audit`, API, TenantGate | Cross-process DB rate counters, tenant fingerprints, HTTP tests | Production auth, proxies, audit retention |
| 8 | Multi-hour soak + Prometheus | `tools/soak.py`, `metrics.py`, `monitoring-soak.yml` | Authenticated metrics API and 60s historical soak | Run 1–2h workflow on runner |
| 9 | Windows Job Objects | `windows_job.py`, `windows_native_smoke.py`, CI matrix | Windows test script wired, not executed on Linux | Execute `Validate_Windows.bat` on native Windows |
| 10 | Manual GitHub release | `prepare_github.py`, `MANUAL_GITHUB_RELEASE.md` | Non-mutating preflight | User chooses repo and pushes manually |

A "present" code path is not a completed security attestation. Restricted multi-tenant mode **still forbids external agents including Docker/VM**. Neither API authentication nor a VM flag makes hostile workloads safe. No account-authenticated provider tests or public publishing has been performed.

## Running live validation on a disposable test host

```bash
python -m pip install -e '.[test,server,postgres-pool]'
python -m pytest -q
python tools/fault_worker_smoke.py --json validation-worker-crash.json
# PostgreSQL CI: configure a disposable test database first
AGENTFLOW_TEST_POSTGRES_DSN='postgresql://TEST_USER:TEST_PASSWORD@127.0.0.1:5432/TEST_DB' python -m pytest -q tests/test_v080_pg_integration.py tests/test_v090_pg_integration.py
python tools/soak.py --seconds 3600 --workers 4 --rate 20
```

For a network partition test, use the test PostgreSQL container attached to a disposable test Docker network and set `AGENTFLOW_TEST_POSTGRES_DSN`. The script explicitly requires `--allow-disruption`, disconnects the selected container, checks that SQL connectivity breaks, reconnects in `finally`, then verifies SQL can recover. **Never run on production, a shared network or a data-bearing database.** A process kill or network failure may leave external effects uncertain; do not replay without review.

```bash
python tools/network_fault_smoke.py --container disposable-postgres --network test_internal --allow-disruption
```

## Security policy

`ScopedSecrets` only exposes explicitly allowlisted environment values to trusted callers. `EgressPolicy` supports pinned-IP HTTPS GET to exact hostnames; it rejects private, loopback, link-local, redirected or non-HTTPS destinations. These APIs are **not applied automatically to arbitrary external agent binaries**. Docker Sandbox keeps networking disabled. Do not feed untrusted workloads secrets in prompts. Rotate credentials via your deployment environment; there is no at-rest vault and no guaranteed secret masking in arbitrary plugin output.

## API changes

- `GET /api/metrics` emits Prometheus text with bounded state labels. Bearer auth is mandatory; it is deliberately not an unauthenticated `/metrics` endpoint.
- `GET /api/audit` returns action, resource identifier and hashed actor fingerprint, not token or prompt contents. In restricted tenant mode this endpoint is admin-only.
- Rate limits default to 600 authorized API calls per actor per minute in a database-backed fixed window; custom limits via `agentflow serve --rate-limit N`. A 429 response has `Retry-After`.
- PostgreSQL `AGENTFLOW_PG_POOL_SIZE=0` means no pool; values 1..64 require `[postgres-pool]` extras. Pool is per Python process. PostgreSQL schema advances 1 to 2; SQLite schema advances 4 to 5.
- Workflow templates can reference **direct** dependencies via `{{steps.step_name.result}}`. Substitution happens once, with output-size checking. Untrusted upstream text remains untrusted: approval, isolation and review are still mandatory for external agents.
