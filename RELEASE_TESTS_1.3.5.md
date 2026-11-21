# AgentFlow Runtime v1.3.5 — reproducible validation evidence

Host: containerized Linux, Python 3.13, pytest 9.0.2. Source: the extracted v1.3.4 release archive with the v1.3.5 changes described in `RELEASE_1.3.5.md`.

| Command | Observed result |
|---|---|
| `python -m pytest -q tests/test_ci_source_guard.py tests/test_core.py tests/test_adapters.py tests/test_github_publication_preflight.py` | 42 passed, 0 failed |
| `python -m pytest -q -ra` | 217 passed, 14 skipped, 0 failed; 73.61 seconds |

Skipped tests require Windows-native handles/Job Objects, delegated cgroup v2, or disposable PostgreSQL services; **skipped is not passed**. Do not copy these numbers into GitHub Actions badge claims; hosted matrix execution of this precise source revision is NOT VERIFIED at packaging time.

The supplied 2026-11-21 GitHub Actions log exports for older SHA `2c8d34b` are analyzed separately in `RELEASE_1.3.5.md`. No real Codex/Claude/OpenCode API calls were run.
