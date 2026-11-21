# Manual GitHub release checklist (operator action only)

AgentFlow is **not** uploaded to GitHub or PyPI by this project generator. There are no artificial stars, downloads or user claims. This document is intentionally manual as requested.

1. Inspect every file and run `python tools/prepare_github.py --json` (offline patterns and risky files, **not** a complete secrets or Git history audit). Read [GITHUB_RELEASE_CHECKLIST.md](GITHUB_RELEASE_CHECKLIST.md) before staging files.
2. Run `python -m pytest -q` on a host with appropriate dependencies, inspect `RELEASE_TESTS.md`, and obtain actual CI evidence before claiming cross-platform support. Use a secret scanner and manually inspect included historical `validation/` logs/screenshots; the basic preflight is insufficient to prove no sensitive data is present.
3. Create a **public** GitHub repository yourself. Check that the repository name and third-party licenses do not conflict.
4. From the extracted project directory:

   ```sh
   git init
   git add .
   git diff --cached --check
   git commit -m "Initial public v1.3.1 beta candidate"
   git branch -M main
   git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_PUBLIC_REPOSITORY.git
   git push -u origin main
   ```

5. Enable GitHub Actions and run the normal CI, PostgreSQL integration and Docker isolation smoke workflows. If a native host test fails, fix it **before** describing the feature as verified.
6. In Repository Settings enable private security reports, branch protection and restricted workflow permissions. Set secrets only via GitHub's protected mechanisms.
7. Only after separate owner authorization, a new Windows/macOS CI review, and successful checks, publish a `v1.3.1` **pre-release**, explicitly experimental. The manual artifact workflow cannot publish to PyPI. Do not enable a publishing workflow without a separate review and approval.
8. Share examples with potential maintainers, invite reproducible bug reports and avoid asking for artificial stars.

Never upload `.env`, local databases, authentication tokens, private logs, customer prompts, or organization-specific source code.
