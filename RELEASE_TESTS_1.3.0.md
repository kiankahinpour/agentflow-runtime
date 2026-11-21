# v1.3.0 validation evidence — 2026-11-21

Source base: `AgentFlow_Runtime_v1.2.9_Public_Beta_Candidate.zip`.

Host: Linux container, Python available in the runtime; **not** a Windows/macOS native runner.

Targeted regression command:

```sh
python -m pytest -q tests/test_egress_url_hardening.py tests/test_v090.py tests/test_public_beta_gates.py tests/test_release_verifier.py
```

Observed: **55 passed in 2.74 seconds** (exit status 0). All new HTTPS URL hardening tests were included. No external requests were made by the new tests.

An attempted full-suite `python -m pytest -q` exceeded the execution time budget and was terminated; **full regression NOT VERIFIED**. The timeout is not evidence of a product deadlock or test failure. The targeted log is stored separately in the automation execution environment and is not included in this source ZIP.

No real Windows/macOS CI, native packaging, PostgreSQL/Docker network faults, pinned QEMU guest, long soak, paid models, GitHub or PyPI publishing was performed. Those remain **NOT VERIFIED**.
