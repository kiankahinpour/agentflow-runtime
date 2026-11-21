## Summary

Explain the problem and how the change addresses it. Link the related issue (e.g., `Fixes #123`).

## How to reproduce and verify

- **Before (for bug fixes):**
- **After:**
- **OS / Python versions actually tested:**
- **Commands and results:**
- **Skipped / blocked / not verified:**

## Safety and compatibility

- [ ] I did not include credentials, private prompts, proprietary source, unredacted logs, or databases.
- [ ] I checked that the change does not enable untrusted multi-user agent execution or weaken authorization/isolation checks.
- [ ] I documented any schema, API, security-boundary, or behavior changes.
- [ ] I used offline fixtures and did not invoke paid model APIs without separate authorization.
- [ ] I added or updated regression tests where appropriate (or explained why not).
- [ ] I ran `python tools/prepare_github.py --json` (or explained why it was blocked).

## Notes for reviewers

Describe unresolved risks and what remains **NOT VERIFIED**. Do not describe a successful mock as live-provider or production isolation validation.
