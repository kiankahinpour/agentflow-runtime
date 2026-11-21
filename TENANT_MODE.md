# Restricted multi-tenant API pilot

Separate SQLite file and queue for each configured tenant. Each tenant credential is a SHA-256 hash of an independently generated high-entropy bearer token; raw tokens are not stored in configuration. Roles are tenant-wide: viewer reads all tenant jobs/results/events; submitter additionally creates jobs and workflows; admin also approves/cancels/resolves/recovers and ticks workflows. Users within the same tenant are not isolated from each other's data. Credentials are statically configured; restart to rotate/revoke. The app rejects credential reuse across tenants, unsafe path names, symlink DB paths and existing external jobs/workflow specs. Only built-in Echo and word-count adapters are available; no custom plugins, external AI, arbitrary shell, or webhook intake in tenant mode. The tenant server serves API only, not the operator dashboard. Local shell/DB access remains fully trusted.

Generate secrets with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Store each token separately in a password manager. Compute its SHA-256 hash locally and put the digest into a protected JSON configuration file (do not commit the file):

```json
{"team-a":[{"sha256":"REPLACE_WITH_64_HEX_DIGEST","role":"admin"}],"team-b":[{"sha256":"REPLACE_WITH_DIFFERENT_64_HEX_DIGEST","role":"submitter"}]}
```

```sh
agentflow tenant-serve --root ./tenant-data --config tenants.json
agentflow tenant-worker --root ./tenant-data --tenant team-a
agentflow tenant-worker --root ./tenant-data --tenant team-b
```

Send `Authorization: Bearer <raw token>` to `http://127.0.0.1:8787/t/team-a/api/jobs` and the equivalent per-tenant paths. A fresh root directory controlled only by the operator is required, with no local untrusted writer. Keep server local. Files are not encrypted, audit events are not tamper-proof and do not record per-principal attribution, and quotas/rate limits, SSO, distributed coordination, resource isolation, network controls, TLS termination, secret broker and a security review are still missing. The API caps individual POST bodies at 1 MiB, not total traffic/storage.

**This is not a production multi-user service or a sandbox for untrusted coding agents.** Do not grant tenant users host access; do not enable external workers against tenant DBs. Separate databases give API-level isolation within the tested model, not an OS process boundary. For executing untrusted code, use independently validated disposable VMs or equivalent isolation with distinct identities, restricted I/O, resource limits and no inherited secrets. Windows/cgroups process lifecycle controls are not privilege boundaries.
