# Public beta publishing policy (operator-only; nothing published)

The v1.3.1 manual `.github/workflows/release.yml` builds and uploads **unsigned distribution artifacts only**; it does not publish to GitHub Releases or PyPI and needs a manually supplied exact source version. Package metadata is dynamic in `pyproject.toml`; `tools/check_release_version.py` checks the canonical `src/agentflow_runtime/_version.py`. Any future publishing workflow requires a separate change, independent review and explicit owner approval.

# Publishing and early adoption (not published)

The PyPI distribution `agentflow-runtime` is already occupied by an unrelated project (https://pypi.org/project/agentflow-runtime/). This release uses provisional distribution name `agentflow-durable`; availability is not confirmed. Check PyPI and branding before creating the public repository. Keep the Python import `agentflow_runtime` and CLI `agentflow` for source compatibility. Use a dedicated virtual environment to avoid clashes with similarly named packages. Do not run `pip install agentflow-runtime` expecting this code.

1. Create an empty public repository under your own GitHub account after reviewing the source, license and package name. Initialize locally and commit the extracted source (exclude database files, credentials, virtualenvs and private outputs). Push to the repository you own. Do not push to any existing third-party project.
2. Run CI on Linux and Windows and the dedicated PostgreSQL service workflow. Confirm that the native Windows process-tree test is not skipped on the Windows runner. Review the logs. The optional cgroup test also requires a delegated cgroup host.
3. (FUTURE ONLY; not yet authorized) Configure a PyPI pending Trusted Publisher for your chosen unclaimed distribution name, repository owner/name, `.github/workflows/release.yml` (workflow filename `release.yml`), environment `pypi`. Configure required human reviewers and restrict the environment to your release branch. Review workflow dependencies and pin actions to audited commit SHAs before production use. See https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/.
4. Manually trigger the artifact-only workflow with exact version `1.3.1` if hosted CI checks pass; download and verify the unsigned artifacts. GitHub Releases and PyPI remain entirely manual, separately authorized future actions.
5. Invite independent beta testers to try the offline demo, then the adapters they already have installed. Ask for reproducible issues and compatibility reports. Publish truthful benchmark methodology, label limitations, and prioritize defects. Track genuine usage, dependencies, issues, PRs, and downloads. No purchased stars or simulated adoption.

The provided package is local only. GitHub/PyPI authentication and ownership are not configured in the development environment. Real provider testing may consume quota and is not part of automatic CI.
