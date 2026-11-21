# GitHub intake and maintenance workflows (0.7.0)

This release accepts signed GitHub issue and pull request webhooks, converts a bounded subset of their metadata into two linked, approval-gated jobs, and stores the workflow durably. It does not fetch PR diffs, run tests from PR code, checkout forks, post comments, open PRs, merge, push, publish, or use GitHub credentials. The default review adapter is Echo (a demonstration, not AI). The external adapter selector is experimental and requires a trusted operator and workspace.

## Local dry run (no account needed)

```sh
python -m pip install -e ".[server,test]"
python tools/github_demo.py
```

A manual GitHub Actions workflow (`maintenance-demo.yml`) runs exactly this offline smoke scenario. It uses no secrets or write permissions. It has not been run on GitHub-hosted CI yet.

## Local webhook receiver

Generate two independent secrets using `python -c "import secrets; print(secrets.token_urlsafe(32))"` and set `AGENTFLOW_TOKEN` and `AGENTFLOW_GITHUB_SECRET` in your environment. On PowerShell use `$env:NAME = 'generated-value'`. Never commit secrets.

```sh
agentflow --db local.db serve --github-repo OWNER/REPO
# Separate terminal:
agentflow --db local.db worker --workflows
```

To receive real deliveries configure a repository webhook for Issues and Pull requests with the secret, JSON content type and HTTPS endpoint `/hooks/github`. Do not make the single-operator server public. Use a dedicated reverse proxy/relay that exposes only `/hooks/github`, validates TLS, limits request size/rate/time and avoids logging sensitive bodies. Keep the authenticated management API on loopback. A real delivery requires repository-admin access and infrastructure; no real delivery has been exercised in this environment.

The receiver verifies HMAC-SHA256 over the raw request body, limits payloads to 256 KiB, requires an explicit case-insensitive repository allowlist, accepts selected event actions, and deduplicates accepted payloads by SHA-256 digest and delivery ID. New stages require operator approval in the dashboard or CLI. In the unlikely case of the same payload with a different delivery header, the existing workflow is returned; accepted payloads are retained for deduplication. The delivery header is not signed. This is not a complete webhook gateway or DDoS defense. Webhook payloads are stored as untrusted text, not executed as code. A malicious issue can still prompt-inject an external model; prompt wording and approval are not a sandbox.

To test an actual external adapter with a trusted local workspace, enable it explicitly both in the server catalog and on the worker, e.g. `--github-adapter codex` on `serve` and `--codex-workspace /trusted/path` on `worker`. The selected adapter may have local permissions; do not enable for untrusted workloads. No GitHub write integration is present, and the CLI provider can have its own credentials/network outside AgentFlow control. Prefer the offline default until OS isolation is available.

Official protocol: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries and https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks.
