# AgentFlow Runtime v1.3.4 — CI matrix failure fixes

**Status:** source-only Public Beta candidate; not an independently validated release on all platforms. **No GitHub push, tag, PyPI upload or API call was performed in this work session.**

## Evidence received

An uploaded GitHub Actions log archive (`logs_121485977839.zip`) contains complete pytest output from nine runs for the published v1.3.2 commit. The observed outcomes:

| GitHub runner / Python | Recorded result |
|---|---|
| Ubuntu / 3.10, 3.12, 3.13 | 201 passed, 14 skipped in each run |
| macOS / 3.10, 3.12, 3.13 | 1 failed, 188 passed, 26 skipped in each run |
| Windows / 3.10, 3.12, 3.13 | 1 failed, 188 passed, 26 skipped in each run |

These numbers are quoted from the supplied CI logs and **not results for this source candidate**.

## Confirmed root causes

1. macOS: a Codex adapter timeout correctly raised `subprocess.TimeoutExpired`, but POSIX group cleanup attempted `os.killpg(pid, SIGKILL)` after a TERM signal and received `PermissionError: [Errno 1] Operation not permitted`. The cleanup exception masked the expected timeout. This is not evidence that all descendants were terminated.
2. Windows: the release preflight correctly recognized a deliberately fake credential, but its error included `validation\old.log`. The test expected the platform-neutral path `validation/old.log`.
3. A Starlette `httpx` deprecation warning was seen on the runners, but did not cause the failures.

## Changes

- Add `_stop_posix_group` with best-effort TERM/KILL semantics and a guarded fallback to `Popen.kill` for the direct child when group signalling is denied or a group is missing. A denied group signal sets the containment result to uncertain. A leader that cannot be reaped is reported as an explicit cleanup error.
- Display paths in the offline publication preflight with `Path.as_posix()` so security findings and test expressions behave consistently across platforms.
- Add targeted synthetic regression tests for group-signal denial, dead groups and preserving the task timeout. These tests do **not** certify actual macOS descendant cleanup.

## Validation and limitations

See `RELEASE_TESTS_1.3.4.md` for the exact tests executed in this environment. This host is Linux. macOS and Windows fixes are based on the failure traces and deterministic tests; both must be verified by fresh hosted CI. Do not represent this as an isolated, multi-tenant workload runner. Real PostgreSQL fault injection, Docker isolation, QEMU boot, package signing and native builds are not verified.

## Operator procedure

Extract the full source archive, review changes and the staged Git index, and commit/push only with owner authorization. In GitHub Actions, verify all nine OS/Python jobs independently. If failures remain, save the raw logs and resolve each root cause before a public binary release.
