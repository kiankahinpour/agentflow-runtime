# AgentFlow Runtime 1.2.0

This release adds `python tools/verify_release.py path/to/AgentFlow_Runtime_v1.2.0.zip`. It validates every file against SHA256SUMS.txt without extracting untrusted paths. The checksum manifest is **not signed**; a malicious actor who can replace both archive and manifest can bypass integrity checking. Verify provenance separately.

Nine dedicated tests passed locally. Full-suite regression did not finish in this run; do not treat this as a fully validated release. Native CI, Docker/PostgreSQL, QEMU and live providers remain unverified.
