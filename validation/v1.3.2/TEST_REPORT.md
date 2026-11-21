# Linux local validation — v1.3.2 (2026-11-21)

- `python -m pytest -q tests/test_github_publication_preflight.py`: **19 passed**, exit code 0.
- `python tools/prepare_github.py --json`: **passed** (172 examined files at time of run).
- Full `python -m pytest -q`: **timed out in execution environment** after reaching 33% progress; **NOT VERIFIED** as a complete suite. No full-suite pass claim is made.
- Windows/macOS GitHub CI, native packages, Docker/PostgreSQL, QEMU, paid providers: **NOT VERIFIED** in this release.
