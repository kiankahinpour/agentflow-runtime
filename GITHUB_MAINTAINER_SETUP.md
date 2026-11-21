# GitHub maintainer setup — public beta v1.3.5

**Repository:** https://github.com/kiankahinpour/agentflow-runtime

This is an **operator checklist**, not a claim that account-level settings are already enabled. Settings names may differ with GitHub updates and plan eligibility. Never publish credentials in issues or commits.

## 1. Repository visibility and About

- [ ] Confirm **Public** visibility and verify the MIT license is detected.
- [ ] Use a concise description and Topics such as `ai-agents`, `python`, `workflow-engine`, `fastapi`, `sqlite`, `agent-orchestration`.
- [ ] Keep Issues enabled; enable Discussions only if you intend to moderate them.
- [ ] Review the public README for current beta limitations and a working quick start.

## 2. Security (owner action required)

- [ ] Under **Settings → Security** / **Code security and analysis**, enable **Private vulnerability reporting** if offered; test that the Security tab presents the private reporting path. Do not publicly solicit exploit details.
- [ ] Enable **Dependabot alerts** and, if available, **Dependabot security updates**.
- [ ] Enable **Secret scanning** and **Push protection** where the plan/repository settings allow them; review existing alerts and Git history. Git ignore alone does not remove leaked credentials from earlier commits.
- [ ] Enable **CodeQL default setup** or another appropriate static analysis workflow, when supported; verify actual results before advertising coverage.
- [ ] Configure **Actions → General** default `GITHUB_TOKEN` permissions as **read repository contents** unless a reviewed workflow requires more.
- [ ] Review pending third-party actions and maintainers' account security, including 2FA/passkeys.

## 3. Protect the main branch

- [ ] **Settings → Rules → Rulesets** (or branch protection) for branch `main`: block force pushes and deletion.
- [ ] Require relevant passing checks from actual CI job names, after the checks are present for a PR: nine matrix jobs, plus PostgreSQL/Docker if these run consistently for PRs.
- [ ] Prefer PR review over direct pushes; **do not require external approving reviews while you are the only reviewer**, or you may block your own maintenance workflow.
- [ ] Review any bypass permissions carefully. Start with a draft ruleset to avoid accidentally locking yourself out.

## 4. Contributor onboarding

- [ ] Merge the community file patch via a reviewed commit/PR; keep the existing beta tag immutable.
- [ ] Confirm bug/feature templates and pull-request template appear in GitHub UI.
- [ ] Review Dependabot PRs; do not auto-merge dependency changes without CI and change review.
- [ ] Create the reviewed public issues from `ISSUE_DRAFTS` after checking duplicates. Keep draft 02 (possible sensitive OpenCode argv exposure) in **private security triage**, not a public issue, unless its disclosure is explicitly cleared. Add only labels that actually exist, or create them.
- [ ] Add one small documentation/test issue labeled `good first issue` and reserve safety-sensitive runtime fixes for experienced reviewers.
- [ ] Periodically update the ROADMAP and triage issues with reproducible evidence.

## 5. Before publishing binaries or new releases

- [ ] Confirm source provenance, exact commit SHA, clean `git diff --cached`, no sensitive files, and passing CI.
- [ ] Build executables on **native hosts** and run smoke tests before attaching them.
- [ ] State explicitly whether signatures, PostgreSQL fault injection, Docker isolation, QEMU guest, long soak, and live providers were tested; do not invent results.
- [ ] Do not enable or publish paid provider runs, GitHub write automation, or PyPI upload without separate explicit approval.
