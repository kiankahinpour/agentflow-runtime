# AgentFlow Runtime v1.3.2 — Git index preflight

This source-only maintenance release strengthens public repository preparation. The optional `python tools/prepare_github.py --staged --json` command examines the exact staged Git blobs, preventing a common oversight where a secret is staged and then deleted from the working tree without restaging. It also rejects staged symlinks, submodules, private filenames, generated folders and selected publishing permissions. No publication or provider API call is performed.

**Limits:** Regex detection is not exhaustive. Git history, binary images, and credentials in unrecognized formats require independent review. Hosted CI, native Windows/macOS builds, live PostgreSQL/Docker/QEMU and multi-tenant isolation remain **NOT VERIFIED**.
