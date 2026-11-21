# Contributing

Discuss substantial design changes before implementation. Use a virtual environment and `python -m pip install -e ".[test,server]"`. Add regression tests for fixes and document behavior changes. Run `python -m pytest -q`. Keep the core usable without third-party dependencies. Do not include private data, API keys or generated database files. For adapter changes, demonstrate behavior using offline mocks and state which live integrations were verified. Changes should be small and reviewable.

## Pull request checklist

- State the affected operating system, Python version, adapter and reproduction steps.
- Add a deterministic local regression test, preferably using the offline Echo adapter.
- Run `python -m pytest -q` and `python tools/prepare_github.py --json`; explicitly list unavailable integration tests.
- Never include authentication tokens, real prompts, unredacted production logs or company code.
- For process-tree and QEMU claims, distinguish fake fixtures from native-host tests.
- Do not relax the restricted tenant execution gate or publish packages in a contributor PR.
- File security vulnerabilities privately where the owner has enabled GitHub private reporting, rather than creating a public exploit issue.
