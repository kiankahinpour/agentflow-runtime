# AgentFlow Runtime v1.3.1 — GitHub source-publication preparation (NOT PUBLISHED)

**Base:** `AgentFlow_Runtime_v1.3.0_Security_Hardening.zip` (the newest available source ZIP at authoring time). Prior ZIP files remain unchanged.

## Changes

- Extend `tools/prepare_github.py` to examine nested project files including historical validation logs. Detect risky credential material/file names, symlinks, and publishing markers in the artifact-only workflow. Return a machine-readable summary with `--json` without printing detected secret values. This is a pattern scanner, **not** a Git history audit, dependency vulnerability scan, or independent security assessment.
- Correct `desktop.self_test()` in source mode so its spawned child processes can import the checkout even when pytest's `pythonpath` setting was not exported as the shell's `PYTHONPATH`; frozen binary environments remain unchanged.
- Harden `.gitignore` and `.dockerignore` for local token, vault, database and credential artifacts.
- Run the offline pre-publication scan in CI and the manual distribution build validation job. Switch the destructive disposable PostgreSQL fault workflow to **manual-only** instead of triggering automatically on every pull request.
- Add publication-preflight regression tests, owner-facing manual GitHub checklist, supported-version/reporting guidance, and updated English documentation and version labels.

## Verification and limits

See `RELEASE_TESTS_1.3.1.md` for independently executed local commands and results: final Linux regression **201 passed, 14 skipped, zero failed**. A test failure from the v1.3.0 baseline source-mode desktop subprocess import was reproduced locally and addressed. These local tests are not GitHub-hosted, Windows-native, macOS-native, or a security certification. Do not run paid coding agents, untrusted multi-user tasks, or public API exposure on the basis of these checks.

**Publication:** No GitHub repository/release or PyPI distribution was created, pushed, or modified. Source is ready for owner review; final rights and sensitive-data approval are owner decisions.
