# GitHub source publication checklist — AgentFlow Runtime v1.3.1

**Status: candidate source only; not pushed, released, or published by this package.**

## 1. Owner decisions (required before public exposure)

- Verify that the author(s) hold the rights to publish the source and bundled screenshots/logs under MIT. Check third-party dependencies separately; the LICENSE file is not proof of ownership.
- Decide the exact repository name and PyPI distribution branding. No GitHub organization or PyPI package name has been reserved by this artifact.
- Review `validation/` manually for faces, names, paths, prompts, secrets and proprietary information. Historical logs and screenshots are retained to preserve evidence; a basic pattern scanner cannot clear images.
- Verify `.gitignore` protects local credentials, database files and vaults; it cannot undo secrets already committed in Git history. Review all included example data and tests. Keep local `.env`, databases, private keys, and credentials out of Git history.

## 2. Offline checks in the extracted project root

```sh
python tools/prepare_github.py --json
python tools/check_release_version.py --version 1.3.1
python -m pip install -e '.[test,server]'
python -m pytest -q -ra
python -m compileall -q src tools tests
```

The preflight is conservative but incomplete. Run a dedicated secret scanner and a dependency review before exposing a repository. **Do not commit credentials even if the scanner returns PASS.** If a check fails, fix or clearly label the failure rather than presenting it as a success.

## 3. Manual first push (operator only)

On GitHub, create a **new, empty** repository without auto-creating README, .gitignore or LICENSE. From the vetted extracted source directory:

```sh
git init
# Set Git author identity on your own machine if needed.
git add .
git diff --cached --check
git diff --cached --stat
# Review the full staged diff for secrets and private data before continuing.
git diff --cached
git commit -m "Initial public beta candidate v1.3.1"
git branch -M main
git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git
git push -u origin main
```

Never paste an access token into a command or commit. Use Git Credential Manager or GitHub CLI to authenticate securely. Do not use `git push --force` to overwrite an existing project.

## 4. After the first push

1. Review the **real** GitHub Actions runs for Windows, macOS and Linux and record the exact OS/Python matrix and skips. Existing YAML files are only configurations, not evidence of execution.
2. Enable private vulnerability reporting, Dependabot alerts/secret scanning where available, and a `main` ruleset requiring PR reviews and passing checks. Restrict workflow token permissions.
3. Run optional PostgreSQL/Docker fault labs **manually**, only in disposable CI or your own dedicated test host. Docker/QEMU/network faults are NOT validated by baseline CI.
4. Rebuild unsigned native EXE/APP/AppImage on their respective OS runners. Check actual output and provenance; do not claim signing or isolation certification.
5. Create a **GitHub pre-release** named `v1.3.1` only after a separate maintainer decision. Clearly mark it experimental and localhost-only. PyPI publication is **not** configured or authorized.

## 5. Truthful initial release statement

> AgentFlow Runtime v1.3.1 is an experimental, local-first durable task orchestrator for trusted operators. It includes SQLite recovery, API/dashboard, offline Echo fixtures and opt-in adapters. Source-level tests are documented, but real hosted cross-platform CI, live PostgreSQL/Docker/QEMU resilience, signed binaries and untrusted multi-user isolation have not yet been independently established for this version. Do not expose the API publicly or run hostile agent workloads.

No GitHub stars, adoption, security certification, benchmark generality, or acceptance into funding programs are claimed.
