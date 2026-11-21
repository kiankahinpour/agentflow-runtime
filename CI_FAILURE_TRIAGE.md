# Hosted CI failure triage (v1.3.3 — historical)

The first public v1.3.2 GitHub Actions run showed a failing `tests (ubuntu-latest, 3.12)` job, while other OS/Python jobs were cancelled due to the default fail-fast strategy. A separate PostgreSQL integration workflow failed; the Docker sandbox smoke workflow passed. The root cause of the two failures is **not established** by the annotations alone.

## Evidence collection

1. Open the failed Ubuntu Python 3.12 job and capture the first failing step and its complete stderr, including the final traceback.
2. Repeat for the PostgreSQL integration job; inspect service health and test output.
3. Run the revised matrix with `fail-fast: false`. Every OS/Python combination should now complete independently; a failure must still mark its own job red.
4. Fix the actual failure in code/dependencies/workflow, add a reproducing regression test, then re-run CI.

This change is **not** a fix for a failing test, and does not claim Windows/macOS/Linux validation. Do not mark a release stable on the basis of the matrix configuration alone.

## Update from the nine-job log bundle (2026-11-21)

After disabling matrix fail-fast, the uploaded logs showed 3/3 Linux jobs passing and two distinct failures (3 macOS jobs with process-group EPERM; 3 Windows jobs with a path separator mismatch). The proposed fixes are described in [RELEASE_1.3.4.md](RELEASE_1.3.4.md). Native CI for the fixes remains unverified pending a subsequent GitHub Actions run.
