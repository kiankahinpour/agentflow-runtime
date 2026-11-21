# Contributing to AgentFlow Runtime

Thanks for helping improve this experimental, local-first runtime. We welcome small, reproducible bug fixes, tests, documentation improvements, and carefully scoped features.

## Before opening an issue

- Search existing [issues](https://github.com/kiankahinpour/agentflow-runtime/issues) and pull requests to avoid duplicates.
- Use the **Bug report** or **Feature request** issue template. Include the exact version, OS, Python version, reproduction steps, and expected/actual results.
- Share only **synthetic, redacted** data. Do **not** post secrets, production databases, private prompts, real customer code, or proprietary logs.
- **Security vulnerabilities:** do not file a public exploit report. Follow [SECURITY.md](SECURITY.md) and request a private reporting route if it has not been enabled.

## Local development

Python 3.10+ is supported in the tested CI matrix. Work from a fork and a topic branch:

```sh
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# POSIX: source .venv/bin/activate
python -m pip install -e ".[test,server,secrets]"
python -m pytest -q
python tools/prepare_github.py --json
```

Some tests are OS-specific or require optional infrastructure. Skips do not count as passes. Identify exactly which host and integration tests you ran. Use the built-in **Echo** adapter and disposable data for most tests; no live AI provider or paid API is needed.

## Pull requests

1. Discuss large API, schema, security-boundary, or architecture changes before implementing them.
2. Keep PRs focused; explain the problem, change, reproduction, and any compatibility implications.
3. Add a deterministic regression test for a bug fix; include a failure-before/fix-after comparison when possible.
4. Run the relevant tests and pre-publication scanner. Clearly identify tests that were not run or were skipped.
5. Update the README, CHANGELOG or ROADMAP if externally visible behavior changes.
6. Complete the pull request template. Avoid unrelated formatting changes and generated archives.

Maintainers review all PRs; contributions are not automatically merged. Do not weaken safety checks, turn on untrusted multi-user adapter execution, or add publishing/paid provider operations without explicit maintainer approval.

## Trust and safety boundaries

- Run tests as an unprivileged user on your own machine or disposable CI infrastructure.
- Never point destructive or fault-injection scripts at production services, personal accounts, or other people's processes.
- Real model/provider integration requires separate explicit authorization and budget review.
- Process containment, VM isolation, and Docker restrictions are **not** independently proven security boundaries for hostile workloads.

## Community standards

Read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Be respectful and specific in code reviews. For an initial contribution, prefer a documented, testable issue labeled `good first issue` rather than modifying privileged process execution or secret handling.
