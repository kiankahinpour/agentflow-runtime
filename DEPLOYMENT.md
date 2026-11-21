# AgentFlow Runtime v0.8.0: PostgreSQL and multi-process deployment

## Scope and assurance

This is an **experimental trusted-operator deployment**. PostgreSQL synchronizes queues, leases, state transitions, workflow ticks and GitHub replay fences among worker processes or hosts using a database-level transaction advisory lock. This does not make side effects exactly-once, does not sandbox workers, and does not make the REST API safe for the public Internet. Use one controlled organization on a private network. Never expose PostgreSQL publicly.

The existing restricted multi-tenant mode intentionally remains **SQLite + safe built-ins only**; it is not converted to PostgreSQL, and it cannot run arbitrary external adapters. Host-level multi-tenancy is **not** certified by this release.

## 1. Single-host Docker Compose (trusted-only)

Prerequisites: a functioning Docker Engine and Compose v2 on an administrator-controlled host; image builds and dependency downloads need network access during setup. This project does not mount `/var/run/docker.sock` into API or worker containers.

```sh
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(36))"
# Set independent, strong AGENTFLOW_DB_PASSWORD and AGENTFLOW_TOKEN in .env.
docker compose up -d --build
docker compose ps
```

The API port is published on **127.0.0.1:8787 only**. The PostgreSQL service has **no published port**. The internal Docker network is private. For another host, use an explicitly managed private tunnel or reverse proxy with TLS and network controls; do not publish the API without external authentication and hardening.

Create a job using your bearer token (do not store real secrets in shell history). The control plane is reachable at `http://127.0.0.1:8787`. Run additional trusted worker replicas:

```sh
docker compose up -d --scale worker=3
```

The worker exposes the deterministic Echo and Word Count adapters. No arbitrary CodeX or host Docker agent is enabled in the Compose example. Use `docker compose down` to stop services; **do not** use `docker compose down -v` unless you intentionally want to delete persisted PostgreSQL data.

## 2. PostgreSQL via CLI without Compose

Install the optional driver:

```sh
python -m pip install -e '.[server,postgres]'
```

Provision a *dedicated* PostgreSQL database and a least-privileged application user. Pass a properly URL-encoded connection URI through the environment (do not place passwords in command arguments):

```sh
export AGENTFLOW_POSTGRES_DSN='postgresql://app_user:REDACTED@db.internal:5432/agentflow'
export AGENTFLOW_TOKEN='SET_A_LONG_RANDOM_TOKEN'
agentflow serve
# another shell/host with same DSN:
agentflow worker --workflows
```

On Windows use equivalent PowerShell `$env:` assignments. Only use different hosts with trusted internal networking, verified time synchronization (NTP), TLS between hosts and PostgreSQL, and a database configured for correct durability. Each worker receives a unique lease token; stale lease completions cannot change the recorded result. **External effects are not fenced by PostgreSQL**. Expired external tasks are marked `uncertain` rather than replayed automatically.

### Transaction and capacity model

- The PostgreSQL backend uses **one advisory lock per write transaction**, including claiming tasks and creating workflow steps. This prioritizes correctness, not maximum throughput. Agents can run concurrently after claiming.
- Table and index definitions are created idempotently for a fresh PostgreSQL store; schema version is recorded in `agentflow_schema` (PostgreSQL schema v1).
- A pre-existing SQLite database is **not automatically migrated**. Keep v0.7+ SQLite installations isolated; do not point both stores at the same queue workload.
- PostgreSQL backup/restore require separate `pg_dump`/`pg_restore` by an operator on a halted or otherwise safely fenced deployment. The SQLite `backup` and `restore` CLI commands are intentionally unavailable in PG mode. Never resume restored in-flight agent jobs automatically.
- State-changing operations open separate database connections. Connection pooling, leader-election optimization and network partition simulation are future work.
- The PostgreSQL driver is optional: install `[postgres]`. With no driver, AgentFlow rejects `AGENTFLOW_POSTGRES_DSN` on startup instead of silently falling back to SQLite.

## 3. Optional Docker sandbox worker (not inside Compose)

This feature runs one **operator-selected** digest-pinned container image per task. It needs a separately managed Docker daemon (not accessible to API users) and does not require/allow mounting a Docker socket into a worker container. Default security controls include no network, no mounts, non-root UID, read-only root filesystem, no Linux capabilities, no-new-privileges, capped processes, CPU, memory and output, temporary scratch and an enforced wall-clock time limit. Job prompts enter the container over stdin. The selected image/command must read stdin and write a plain-text result to stdout.

```sh
# Operator preloads/trusts the exact image digest. Replace IMAGE_DIGEST with
# a real, locally available digest; no image is pulled during a job.
agentflow worker --sandbox-image 'example.org/agent@sha256:IMAGE_DIGEST' --sandbox-command cat
```

For API submission, start a separate authorized single-operator server with `agentflow serve --enable-sandbox`; this only lists the queue target and **does not** grant API access to Docker. Approve sandbox tasks manually. To test on a machine with Docker: `python tools/docker_smoke.py --image REAL_PINNED_IMAGE --command cat`.

**Security warning:** Docker isolation is not a proven security boundary against malicious/hostile multi-tenant workloads, kernel exploits, or compromised container runtimes. Docker daemon access often grants host-level power. For untrusted users, use a hardened dedicated VM or microVM per tenant/job with independent identities, secret isolation and verified egress controls. Do not run the host's code-agent credentials inside a hostile sandbox. This sandbox is intentionally **disabled** in restricted multi-tenant mode.

## 4. Validation

```sh
python -m pip install -e '.[test]'
python -m pytest -q
```

Tests for the PostgreSQL driver and real PostgreSQL service require `AGENTFLOW_TEST_POSTGRES_DSN` referencing a fresh **disposable test database** and `pip install '.[test,postgres]'`. GitHub Actions includes `postgres-integration.yml` with a PostgreSQL service, but it must run on GitHub to count as a live integration check. Docker containment likewise requires a live daemon and a digest-pinned local image. Neither is available in the original Linux build environment.

## 5. Before a public release

Validate real database failover, clock skew, network partition, crash during Docker container launch, Windows Job Objects, resource and egress controls, CI on real PostgreSQL, and a threat model for each deployment. Establish real independent users and collect issue reports before claiming production readiness.

### CI Docker sandbox smoke

The separate `.github/workflows/docker-sandbox.yml` job pulls a test image, obtains its repository digest and runs the restricted container echo smoke on an Ubuntu GitHub runner. This is **not yet evidence of a passing run** until a public repository executes and records that job. Container/daemon escape resistance is not covered by the smoke test.
