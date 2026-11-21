> **v1.3.1 Public Beta candidate — source package only; not published to GitHub or PyPI.** This is experimental local-first software, not a certified sandbox or a production security guarantee. See [RELEASE_1.3.1.md](RELEASE_1.3.1.md), [RELEASE_TESTS_1.3.1.md](RELEASE_TESTS_1.3.1.md), [SECURITY.md](SECURITY.md), and [MANUAL_GITHUB_RELEASE.md](MANUAL_GITHUB_RELEASE.md).

# AgentFlow Runtime — experimental local-first task orchestration

**Release evidence:** v1.3.1 adds local GitHub-preflight hardening and an offline desktop smoke fix. See [RELEASE_TESTS_1.3.1.md](RELEASE_TESTS_1.3.1.md) for newly executed tests and gaps. An operator-provided Windows 11 x64 Codex validation report for the corrected v1.2.8 source described 151 passed / 26 skipped tests and a native EXE smoke check. Those raw Windows logs and the executable are **not part of this source ZIP** and have **not been independently reproduced for v1.3.1**. v1.2.9 adds bounded API request processing and release workflow safeguards, with separately documented local results. Hosted Windows/macOS/Linux CI, PostgreSQL/Docker fault injection, real QEMU guest boot, authenticated agent execution and independent security review are **NOT VERIFIED** for v1.3.1.

**Safety boundary:** Use only for a single trusted local operator with localhost binding. Unauthorized POSTs to `/api/` are rejected before body parsing, and authenticated API POST/PUT/PATCH bodies are capped at 2 MiB. This is not a distributed DoS defense; GitHub webhooks have their existing independent limit. SQLite prompts/results are plaintext and external coding agents execute with the privileges of their configured process. Do **not** expose the API publicly or permit untrusted multi-user agent execution.

**Quick launch:** `Start_AgentFlow_Windows.bat`, `sh Start_AgentFlow_Linux.sh` or `sh Start_AgentFlow_macOS.command`. These launchers run only the offline built-in adapters on localhost and create a local API token; they may download Python dependencies and require Python 3.10+ and internet for first install. Run `python tools/doctor.py --json` for non-invasive host diagnostics. For signed audit logs set a high-entropy `AGENTFLOW_AUDIT_HMAC_KEY` before starting the server/worker, then use `agentflow audit-verify` and retain the returned tip separately.

**v0.9.0:** audit, rate limiting, VM adapter, workflow result handoff, optional PostgreSQL pooling and observability. **v0.8.0:** optional PostgreSQL coordination for multiple trusted workers/hosts; opt-in Docker execution with no network, read-only filesystem and resource caps; Docker Compose demo and optional live integration checks. See [DEPLOYMENT.md](DEPLOYMENT.md) and [SECURITY.md](SECURITY.md). The existing SQLite backend remains the default. Neither Docker nor PostgreSQL claims to make arbitrary external agents safe for hostile multi-tenant use. **No public release or live PostgreSQL/Docker validation has been claimed.**


**Experimental local-first durable task orchestration for coding agents.**

AgentFlow separates job submission from execution. It keeps tasks and a durable event history in SQLite, prevents duplicate submissions with idempotency keys, supports explicit human approval, and uses renewable worker leases to fence stale results. Crashes are not silently replayed: an expired running task becomes `uncertain`, because an external action may have already happened.

## Quick start (Python 3.10+)

```sh
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[server,test]"
agentflow submit "hello runtime" --key demo-1
agentflow worker --once
agentflow list
python -m pytest -q
```

The `echo` adapter is an offline demonstration, not an AI model. To keep processing tasks, run `agentflow worker` in a separate terminal. Use `--db path/to/jobs.db` before the subcommand, or set `AGENTFLOW_DB`, in all terminals to share one database.

### Local dashboard

Generate a random API token:

```sh
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set it in the server terminal (replace the sample with your generated token):

```powershell
# Windows PowerShell
$env:AGENTFLOW_TOKEN = 'REPLACE_WITH_YOUR_RANDOM_TOKEN'
agentflow serve
```

```sh
# Linux/macOS
export AGENTFLOW_TOKEN='REPLACE_WITH_YOUR_RANDOM_TOKEN'
agentflow serve
```

Open http://127.0.0.1:8787, enter the same token, submit an echo task, and run the worker in another terminal. The dashboard refreshes the latest 200 tasks every three seconds and shows counts across the entire database. It uses memory-only API authentication. It does not start a worker automatically.

### Codex adapter (experimental)

Install and authenticate the official Codex CLI independently, then configure a trusted workspace (a local Git repository is recommended). No credentials are bundled with this project.

```sh
agentflow submit "Review the repository for missing tests" --adapter codex --approve
agentflow approve JOB_ID
agentflow worker --codex-workspace /path/to/trusted/repository
```

The adapter invokes `codex exec --sandbox read-only --output-last-message FILE -` with the prompt on stdin. See the [official Codex documentation](https://developers.openai.com/codex/) and check your installed CLI's `codex exec --help`. Only the last response is retained. This adapter has not been tested with an authenticated Codex session in the release environment. Sandbox behavior depends on the installed CLI and host; do not use with untrusted users or sensitive workspaces.

### Python SDK

```python
from agentflow_runtime import Store, Worker
from agentflow_runtime.adapters import echo

store = Store('agentflow.db')
job_id = store.submit('hello', idem='example-1', approval=True)
store.approve(job_id)
Worker(store, {'echo': echo}).once()
print(store.get(job_id)['result'])
```

### HTTP API

All `/api` endpoints require `Authorization: Bearer YOUR_TOKEN`. The service binds to loopback. `GET /health` is unauthenticated. The default API is intended for a single local operator and has no built-in TLS. A restricted tenant pilot exists separately, but untrusted multi-tenant execution remains disabled.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/jobs` | Submit with `prompt`, `adapter`, optional `idem`, `approval`, `max_attempts`, `timeout` |
| GET | `/api/jobs?limit=50&offset=0&state=queued` | Filter and page tasks |
| GET | `/api/stats` | Global state counts |
| POST | `/api/recover` | Mark expired leases uncertain |
| POST | `/api/jobs/{id}/resolve` | Resolve uncertain tasks with decision and reason |
| GET | `/api/jobs/{id}` | Inspect job |
| GET | `/api/jobs/{id}/events` | Read audit events; optional `after` sequence and `limit` |
| POST | `/api/jobs/{id}/approve` | Release approval gate |
| POST | `/api/jobs/{id}/cancel` | Cancel queued tasks or request running-task cancellation |

## Execution semantics

- `waiting_approval → queued → running → succeeded / failed / uncertain`; `queued` or `waiting_approval` can become `cancelled`.
- Explicit `max_attempts > 1` enables automatic retries only for the built-in `echo` adapter. All other adapter errors become uncertain and require operator review even with a retry budget. Do not replace the echo adapter with side-effectful code. Default is one attempt.
- A worker renews its lease during execution. If the lease expires, the next worker poll or explicit recovery marks the task uncertain. A stale completion cannot overwrite database state.
- This does **not** guarantee exactly-once external effects or stop an orphan process. Inspect uncertain jobs and external effects before resolving or submitting a replacement. Manual success records the operator decision, not an agent result. Running cancellation is cooperative: `running → cancel_requested → cancelled` only when the adapter confirms a stop; a race with completion or unconfirmed stop becomes `uncertain`. Cancellation does not undo external effects.
- The SQLite database holds prompts and results in plaintext; protect its directory and backups. Read-only Codex mode reduces write risk but is not a substitute for host isolation.

## Recovery and backups

```sh
agentflow recover
agentflow list --state uncertain
agentflow events JOB_ID
agentflow resolve JOB_ID failed --reason "Verified failure and inspected external effects"
agentflow stats
agentflow backup snapshot.db
```

If external effects have been independently verified absent and an attempt remains, use `resolve JOB_ID retry --reason "..."`. All non-echo retries require a fresh approval. Expired workers might still be active; do not retry until they have stopped. `succeeded`, `failed` and `cancelled` are the other operator resolutions. The reason is stored in the immutable-by-API event log; it is not tamper-proof against database access.

Backup uses SQLite's online backup API, includes committed WAL data and refuses an existing destination. Keep backups private. An interrupted backup may leave an incomplete file; verify integrity before restoration. Restore into a new offline database, with all workers stopped:

```sh
agentflow --db restored.db restore snapshot.db
agentflow --db restored.db list --state uncertain
```

Restore refuses existing targets, checks SQLite integrity and schema, and marks snapshot-running and cancel-requested jobs uncertain. **Snapshot-queued tasks enter `restored_hold` and workers cannot claim them.** Review external effects, then use `resolve JOB_ID retry --reason "..."` (non-echo work additionally requires approval), or resolve/cancel as appropriate. An older snapshot can contain tasks that completed after the backup. Tasks already awaiting approval remain held at the approval gate. Never run the original and restored databases as competing queues. Before upgrading from any older release, stop all old workers and back up the database. Schema version 2 adds restored-hold semantics, retaining the active-lease index and refusing newer schemas. Mixed-version workers and downgrade against a migrated database are unsupported.

### Running cancellation and process cleanup

Use `agentflow cancel JOB_ID`, the dashboard Cancel button, or the authenticated API. Workers check cancellation during lease renewal (normally within 250 ms, subject to database contention). Cooperative adapters may opt in by setting `supports_cancellation=True`, accepting keyword-only `cancel_event`, and raising `ExecutionStopped` only when stopped. Legacy two-argument adapters still work but cannot be forcibly stopped. Lost leases also signal the cooperative adapter.

On Linux, a separate supervisor registers as a child subreaper and kills/reaps adopted descendants, including ordinary children that create their own sessions. The fallback scans `/proc/*/stat` if the children file is unavailable. Linux tests cover cancellation, timeout and normal leader exit with detached children. On Windows, the launcher waits for a gate until assigned to a kill-on-close Job Object, then launches the agent; cleanup queries the remaining active process count. Assignment failure blocks launch. Native Windows verification is outstanding. On other POSIX platforms, process-group cleanup remains best effort and cannot confirm all descendants. None of these are a security sandbox or a guarantee against a hostile process, external services, supervisor crashes or worker termination.

## Adapter protocol v1

The worker accepts legacy callables or explicit `AdapterSpec` objects. The local operator registers plugins; requests cannot load code. All non-echo submissions via CLI/API require approval. The trusted Python SDK retains its original explicit `approval` parameter. No plugin should execute arbitrary user-provided commands or assume retries are safe.

```python
from agentflow_runtime import AdapterSpec, Registry, Store, Worker

registry = Registry().register(AdapterSpec('uppercase', lambda p, t: p.upper()))
store = Store('demo.db')
job = store.submit('hello', 'uppercase', approval=True)
store.approve(job)
Worker(store, registry.mapping()).once()
```

To load `examples/custom_plugin.py`, first make `examples` importable (`PYTHONPATH=examples` on POSIX, `$env:PYTHONPATH='examples'` in PowerShell after installation). Launch both `agentflow serve --plugin custom_plugin:PLUGIN` and `agentflow worker --plugin custom_plugin:PLUGIN`. The registry rejects duplicate names and incompatible protocol versions. `GET /api/adapters` exposes configured catalog metadata, not worker liveness or credentials. Codex is a known catalog target even when its worker is absent. `word-count` is a second deterministic offline example; not an AI model.

### Optional Ollama adapter

Install and run Ollama independently with a model already available locally; select that model in both terminals:

```sh
agentflow serve --ollama-model YOUR_LOCAL_MODEL
agentflow worker --ollama-model YOUR_LOCAL_MODEL
agentflow submit "Summarize this text" --adapter ollama
agentflow approve JOB_ID
```

The adapter calls [Ollama's generate API](https://docs.ollama.com/api/generate) on `127.0.0.1` only, with streaming disabled. It does not download a model or redirect requests. The selected model and server are operator-controlled; select a genuinely local model, not a cloud-backed model. Socket timeouts do not guarantee that server-side generation stopped. Cancellation is unconfirmed and errors are uncertain. The HTTP contract is tested with a fake connection only, not a running model.

## Validation tools

```sh
python tools/benchmark.py --jobs 1000 --workers 4
python -m pip install playwright
python -m playwright install chromium
python tools/browser_smoke.py
# Offline rendering + TestClient bridge if browser networking is restricted:
python tools/browser_smoke.py --offline
# Explicit authorization: may consume quota; requires installed/authenticated Codex:
python tools/live_codex_smoke.py --allow-live-call
```

Windows native Job Object tests are in the CI matrix. To run locally on Windows: `python -m pytest -q tests/test_v050.py -k windows_job`. See RELEASE_TESTS.md for measured results and limitations. Browser screenshots and benchmark JSON are in `validation/`.

## Development

```sh
python -m pip install -e ".[test,server]"
python -m pytest -q
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [CHANGELOG.md](CHANGELOG.md), [ROADMAP.md](ROADMAP.md), and [GITHUB_RELEASE_CHECKLIST.md](GITHUB_RELEASE_CHECKLIST.md). Project name and distribution availability must be checked before public release. This is a prototype, not affiliated with OpenAI; no adoption or production-readiness claims are made.

## v0.6.0 monitoring and adapters

The provisional distribution name is `agentflow-durable` (existing `agentflow-runtime` on PyPI is unrelated; use the local wheel until a name is confirmed). Import and CLI remain unchanged. See `PUBLISHING.md`.

- Continuous `agentflow worker` processes report best-effort heartbeats every 2 seconds. `/api/workers` shows PID, adapter list, last heartbeat and current job; after 10 seconds without a heartbeat the status is stale. This is telemetry, not lease ownership. `worker --once` is not registered.
- The dashboard polls the global event feed and worker roster every 3 seconds, with state filtering and search of up to 200 loaded tasks. `/api/events?after=SEQ&limit=100` returns metadata only. `/api/events/stream?after=SEQ&seconds=15` is a bearer-authenticated SSE endpoint with bounded duration (1–30 seconds); reconnect using the last event ID. Dashboard currently polls rather than consuming SSE. Event detail remains available via per-job history.
- Experimental Claude Code and OpenCode adapters are opt-in. Install/authenticate the official CLI independently; check `--help` for your version. Use disposable trusted workspaces and a separate low-privilege identity. Claude runs in print mode with plan mode and built-in tools disabled; external configuration/hooks/MCP may still have effects. OpenCode uses its documented standalone one-shot command with no auto-approve flag. Its prompt is visible in process arguments; never pass secrets. Neither CLI adapter is a security sandbox. For Windows use a native executable; shell wrappers are not validated.

```sh
agentflow worker --claude-workspace /path/to/trusted/workspace --opencode-workspace /path/to/trusted/workspace
agentflow serve --enable-claude --enable-opencode
```

Use `--adapter claude` or `--adapter opencode` on submission; approval is mandatory through CLI/API. Failed external runs remain uncertain and are not automatically replayed.

Real-provider smoke tests (explicitly authorize possible quota usage):

```sh
python tools/live_provider_smoke.py codex --allow-live-call
python tools/live_provider_smoke.py claude --allow-live-call
python tools/live_provider_smoke.py opencode --allow-live-call
python tools/live_provider_smoke.py ollama --model YOUR_INSTALLED_MODEL --allow-live-call
```

## Optional Linux cgroup containment

Set `AGENTFLOW_CGROUP_ROOT` to a dedicated, empty and appropriately delegated cgroup v2 subtree (never the root mount). Each external CLI is gated before launch, attached to its own child cgroup, and cleaned using `cgroup.kill` even if its supervisor dies, as long as the worker remains alive. Failure to configure containment fails closed. No privileged setup is performed automatically. This is not a sandbox; agents with sufficient privileges may escape, and worker crashes can leave cgroups for an operator to inspect and clean. CPU/RAM quotas are not configured by this release. Run native validation only with a dedicated test subtree: `AGENTFLOW_TEST_CGROUP_ROOT=/path/to/delegation python -m pytest -q tests/test_v060.py -k cgroup`. The release environment has a read-only cgroup mount, so the native test is not verified here.

## Multiprocess soak

`python tools/soak.py --seconds 3600 --workers 4 --rate 100` runs a paced synthetic workload across independent processes, checks state counts, duplicate claims, process exit codes and database integrity. No model calls. Start with 60 seconds; longer runs require more disk. See validation reports for actual run duration and outcomes.

## v0.7.0: signed GitHub intake, durable DAGs and restricted tenants

Install with `python -m pip install -e ".[server,test]"`. Try `python tools/github_demo.py` for a signed synthetic webhook and an approval-gated two-step workflow with no external calls. See [GitHub integration](GITHUB_INTEGRATION.md), [restricted tenant API](TENANT_MODE.md) and [security policy](SECURITY.md).

General workflows use a JSON list of up to 32 named steps; dependencies must be acyclic, prompts may include reviewed direct-dependency result templates (`{{steps.NAME.result}}` in v0.9.0); upstream text remains untrusted data. A worker started with `--workflows` advances the coordinator, or an operator can call `workflow-tick`. Non-Echo steps always require explicit approval. A terminal unsuccessful step blocks new stages; already-enqueued or running independent branches are not automatically cancelled. Restored active workflows are held, and are not automatically resumed (review external effects; create a new workflow only after reviewing scope and duplicates). Existing local CLI/API remains trusted single-operator; do not share its token.

```sh
agentflow --db local.db workflow examples/maintenance_workflow.json --key demo-1
agentflow --db local.db worker --workflows --once
agentflow --db local.db workflow-get WORKFLOW_ID
```

The operator dashboard shows recent workflows and offers manual advancement. Use the existing job approval controls. Repository webhooks are opt-in. Multi-tenant mode is API-only and prohibits external providers; it is not a sandbox. Back up the DB before schema v4 migration, and stop old binaries before upgrade.

## v0.9.0 — Reliability, security operations and manual public-release readiness

v0.9.0 adds a database-backed API rate limiter with tenant-scoped actor fingerprints, audit trail and authenticated Prometheus-format metrics (`/api/metrics`); a protocol-tested **experimental QEMU VM adapter** (`--vm-image`, `--vm-sha256`) with no guest network; scoped environment secrets and an explicit DNS-pinned HTTPS egress broker; optional psycopg3 connection pooling (`AGENTFLOW_PG_POOL_SIZE`); and bounded single-pass workflow output handoff (`{{steps.NAME.result}}`). The dashboard displays recent actor/action audit records.

Operators can run subprocess crash injection (`tools/fault_worker_smoke.py`), disposable Docker network fault injection (`tools/network_fault_smoke.py`), long multiprocess soak (`tools/soak.py`) and native Windows validation (`Validate_Windows.bat`). CI definitions exist for PostgreSQL, Docker, Windows and on-demand soak; the actual hosted runs must be performed by the operator. The new VM module is a working integration contract **without a shipped guest image**, not a guaranteed sandbox; trusted host plugins and external agents are not automatically constrained by its policy helpers. Restricted tenant mode continues to prohibit external adapters.

See [v0.9 operator matrix](OPERATIONS_090.md), [VM setup](VM_SETUP.md), [manual GitHub release](MANUAL_GITHUB_RELEASE.md), and [security limitations](SECURITY.md). Neither GitHub nor PyPI has been modified.

## Native desktop build and validation

The build and desktop preflight report the current package version. On Windows,
also run the Job Object, SQLite, and release verifier checks with the development
extras installed.

\`\`\`powershell
python -m pip install -e ".[test,server]"
python -m pytest -v -ra
python tools/regression_guard.py --timeout 90 --report regression-guard-report.json
python tools/soak.py --seconds 5 --workers 2 --rate 20
python tools/benchmark_windows.py
\`\`\`

`agentflow-desktop` provides a local-only server + trusted Echo worker, opening a browser dashboard; it does **not** enable cloud agents. `agentflow-desktop --self-test` verifies local API submission and worker completion without downloading models or contacting outside services. The source launcher is available on Windows, Linux and macOS; **native verified binaries have not been generated in this build environment**.

To build unsigned Windows EXE, macOS `.app`, Linux onedir and optional AppImage **on their respective native hosts**, follow [NATIVE_BUILDS.md](NATIVE_BUILDS.md). A manual, build-only [GitHub Actions workflow](.github/workflows/native-builds.yml) is included. See [REAL_VALIDATION.md](REAL_VALIDATION.md) for which real infrastructure checks still need to be executed and [COMMUNITY_PILOT.md](COMMUNITY_PILOT.md) for an ethical early-adopter pilot.
