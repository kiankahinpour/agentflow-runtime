# AgentFlow Runtime v1.2.1 — bounded archive verification

This patch hardens the offline release archive verifier against resource-exhaustion inputs. It now rejects archives with more than 10,000 entries, individual entries larger than 32 MiB, aggregate uncompressed content over 256 MiB, compression ratios exceeding 1000:1, manifest files over 2 MiB, encrypted entries and non-regular special filesystem entries. SHA-256 verification streams in 1 MiB blocks with an independent per-file read bound.

These are conservative source-release limits, not a generic-purpose ZIP extractor. SHA-256 checksums are not signatures and do not establish publisher authenticity. The verifier is not a security boundary against all ZIP parser vulnerabilities.

Validation: 15 release-verifier tests passed locally, including six new adversarial tests. A full-suite run was attempted but did not complete within the available execution window; full regression remains unverified for this patch. Windows/macOS CI, Docker/PostgreSQL and QEMU validation remain unverified. No network access, paid model invocation, or publication was performed.
