# AgentFlow Runtime 1.2.9 — Public Beta candidate (NOT PUBLISHED)

Source base: `AgentFlow_Runtime_v1.2.8_windows-validated-source.zip`, an operator-supplied ZIP of the corrected Windows-validation source. This release is a candidate for manual public-source review; it does not claim production readiness or security certification.

## Changes

1. The FastAPI middleware refuses anonymous `/api/` POST/PUT/PATCH requests before parsing JSON, avoiding unauthenticated JSON parsing and allocation. Authenticated requests to these routes have a 2 MiB body limit, enforced using Content-Length preflight and bounded streaming even when Content-Length is absent. Other authenticated API dependency checks and database rate limiting still apply.
2. `.github/workflows/release.yml` no longer contains a PyPI publication job, a writable OIDC permission or `publish_pypi` input. It is a manually invoked **artifact-only** build workflow and checks the requested version using `tools/check_release_version.py` against the source's canonical dynamic version.
3. `.github/workflows/native-builds.yml` names artifacts by Git SHA rather than the obsolete hard-coded v1.1.0. README, CHANGELOG, ROADMAP, SECURITY and release documentation reflect this candidate and its limitations.
4. `tests/test_public_beta_gates.py` covers the API request gate, accepted legitimate requests, canonical version and nonpublishing workflow constraints.

## Verification

The local Linux full suite completed with **170 passed, 14 skipped, zero failed** in 73.58 seconds (Python 3.13.5). The local wheel `agentflow_durable-1.2.9-py3-none-any.whl` was built from the source with no published distribution. See `RELEASE_TESTS.md` for commands, skips, limitations and exact evidence. Validation is not a hosted multi-OS run. No model integrations, deployments, public push or publishing occurred. Source ZIP checksums are for integrity only; without a trusted independent signature they do not prove publisher authenticity.

## Known limitations

- The API body cap is **per request** and does not stop slowloris connections, distributed abuse, malicious local processes, or unauthorized access to the SQLite file. Keep default listener on `127.0.0.1`; do not expose to the Internet.
- Authorized prompt size can still reach 100,000 Unicode characters within the cap; any request exceeding 2 MiB is rejected even if its JSON fields might otherwise validate.
- Hostile multi-tenant execution is not supported. External adapters, Docker and QEMU require separate threat review and real-host tests.
- The operator's Windows v1.2.8 report is a supplied claim, not reproducible evidence included in this archive. No v1.2.9 Windows/macOS native build is claimed.
- Project remains experimental. Signed binaries, private security reports and repository protection require manual owner action.
