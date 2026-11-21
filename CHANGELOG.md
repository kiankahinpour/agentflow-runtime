## v1.3.5 — source checkout verification and heartbeat test reliability (2026-11-21)

- Analyze the **new** full GitHub Actions log bundle from public commit `2c8d34b`: the hosted checkout still executed the old POSIX cleanup despite the v1.3.4 caption; Windows Python 3.13 additionally recorded a timing-sensitive heartbeat failure.
- Add a source checkout guard to the CI workflow. It checks canonical version `1.3.5` and the presence of the macOS/Windows fix markers and tests **before** pytest, making incomplete source copies easy to diagnose.
- Rewrite the heartbeat test to observe an actual successful renewal instead of assuming a 300 ms lease survives every Windows scheduling stall. Runtime fencing is unchanged.
- Add offline guard regression tests; update English release evidence and operator upload procedure.
- Local Linux: 217 passed, 14 skipped. **Hosted Windows/macOS CI for v1.3.5 NOT VERIFIED.** No publishing, paid API calls, or production security claim.

## v1.3.4 — CI macOS cleanup and Windows path diagnostics (2026-11-21)

- Analyze the uploaded 9-job GitHub Actions matrix logs: Linux 3/3 passed; macOS 3/3 failed on `os.killpg` `PermissionError` during Codex timeout cleanup; Windows 3/3 failed on a backslash-versus-slash assertion in the publication scan test.
- Handle POSIX process-group `EPERM` without masking the original adapter timeout: attempt process-leader termination only when it is still running, reap it, and leave descendant containment explicitly unverified.
- Format pre-publication diagnostics with forward-slash paths on every OS, keeping the credential-detection behavior unchanged.
- Add local regression tests for denied/missing POSIX process groups, preservation of `TimeoutExpired`, and Windows-style path display.
- This is a source-only candidate. Neither native macOS/Windows execution nor updated hosted GitHub CI has been verified; no public publishing, model invocation, or paid integration was performed.

## v1.3.3 — complete CI matrix evidence (2026-11-21)

- Set `strategy.fail-fast: false` for the 3x3 GitHub Actions test matrix so an Ubuntu failure does not cancel Windows/macOS evidence.
- Add offline regression tests ensuring all OS/Python combinations remain configured and pytest failures are not ignored.
- The user-observed first GitHub CI run for v1.3.2 failed on Ubuntu Python 3.12; other matrix entries were cancelled. The exact failure cause and PostgreSQL integration failure remain UNKNOWN until step logs are collected.
- This change does NOT fix the underlying failing test. New hosted CI execution is NOT VERIFIED.

## v1.3.2 — staged Git index secret preflight (2026-11-21)

- Add optional `--staged` offline gate to examine exact Git index blobs, including tracked files whose working-tree copies have changed.
- Reject staged private filenames, symlinks/submodules, generated paths, credential patterns, and publishing markers.
- Add regression tests proving that secrets staged and then removed from the working tree are still detected.
- This is a best-effort heuristic, NOT a complete secret scan or Git history audit. GitHub CI and cross-platform testing remain NOT VERIFIED.

## v1.3.1 — GitHub source-release preflight and desktop smoke reliability (2026-11-21)

- Scan historical validation text and nested project files before source publication; reject common secrets, private filenames and symlinks without exposing matching values in errors.
- Repair source-mode desktop self-test imports when pytest adjusts import paths without exporting `PYTHONPATH`.
- Add preflight CI checks, require explicit manual triggering for the PostgreSQL Docker fault lab, and publish an owner-operated GitHub readiness checklist.
- Preserve the offline/local trusted-operator safety boundary; GitHub-hosted CI, live providers and strong isolation are NOT VERIFIED for this release.

## v1.3.0 — fail-closed HTTPS egress URL parsing (2026-11-21)

- Validate DNS allowlist hostnames label by label (RFC-style label boundaries and 63-character maximum).
- Refuse raw control characters, whitespace, backslashes, and non-ASCII request targets before DNS; convert malformed URL port errors into policy denials. Encoded URL path/query values remain supported.
- Add deterministic offline regression coverage; no network calls or paid providers are required.
- This is input hardening, NOT a claim of SSRF immunity, multi-tenant sandboxing, or externally audited security. Windows/macOS and live provider testing remain NOT VERIFIED for v1.3.0.

## v1.2.9 — public-beta preparation (2026-11-21)

- Prevent unauthorized API POST requests from reaching JSON body parsing; reject oversized authorized API request bodies (including chunked streaming) before routing. New 2 MiB per-request guard; not an IP quota or substitute for perimeter controls.
- Correct the manual distribution workflow to compare operator-requested version against the canonical dynamic package version; remove all PyPI publishing permissions and steps. The workflow now only uploads unsigned build artifacts after cross-platform validation.
- Replace stale v1.1.0 labels in the native workflow artifact name, update the README release status and add public-beta safety and evidence notes.
- Add local tests for authorization/body caps, source version consistency, and non-publishing workflow.
- The Windows 151 passed/26 skipped report is operator-supplied evidence for corrected v1.2.8, not an independent v1.2.9 Windows run. Cross-platform hosted CI, Docker/PostgreSQL, QEMU, signed binaries and live provider calls remain NOT VERIFIED.

## v1.2.8 — fail-fast regression evidence

### Windows validation fixes

- The regression guard uses a gated Job Object on Windows and checks process-tree cleanup after timeout or normal exit.
- The ZIP verifier validates the original central-directory spelling and rejects ambiguous Windows paths. The verifier checks integrity against the archive manifest without extracting files.
- The browser smoke tool waits through Playwright locators with the dashboard's CSP in force. The soak and chaos tools close the final SQLite connection before deleting their temporary directories.
- Loopback launchers and their health probes use direct HTTP, including on Windows hosts with a configured system proxy. The portable launcher handles a Windows console break through its managed shutdown path.
- Package metadata, API responses, dashboard, desktop preflight, and native build manifests use the same v1.2.8 version. The FastAPI floor now aligns the TestClient dependency with supported HTTPX versions.
- Added Windows regressions for process cleanup, forced SQLite rollback, API concurrency, and short soak cleanup.

- Add optional `--fail-fast` to halt after the first failed/timed-out module without marking the run complete.
- Persist the failure and leave `complete=false`, allowing operators to distinguish aborted execution from a full run.
- Add a focused regression test for fail-fast and checkpoint semantics.
- A diagnostic run with an 18-second per-module timeout identified the slow process-cleanup fixture; this short timeout is insufficient to prove a hang.
- Cross-platform CI, Docker/PostgreSQL and QEMU remain unverified.

