# AgentFlow Runtime v1.3.0 — local security-hardening candidate (NOT PUBLISHED)

Base: `AgentFlow_Runtime_v1.2.9_Public_Beta_Candidate.zip` (latest accessible source ZIP).

## Changes

The trusted-operator HTTPS egress broker rejects malformed allowlist DNS labels and raw request-target characters that could make manually constructed HTTP/1.1 request lines ambiguous. It denies malformed URL ports before DNS resolution and continues to accept properly percent-encoded paths and queries. No network or paid model is needed to test this behavior.

## Security boundary

These are defensive parsing improvements, not an independent security audit or a guarantee against SSRF, untrusted multi-tenant execution, or hostile coding agents. This broker must remain available only to trusted operators. TLS pinning, proxy bypass, DNS rebinding resistance, and real-world egress behavior need independent review.

## Verification

See `RELEASE_TESTS_1.3.0.md` for exact commands, counts and environment. Windows/macOS CI, EXE/APP/AppImage, real PostgreSQL/Docker/QEMU, long soak, and live providers are NOT VERIFIED in this release. No GitHub or PyPI publication occurred.
