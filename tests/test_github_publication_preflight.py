"""Offline tests for public-source safety gates; no GitHub API access."""
import pytest

from tools.prepare_github import REQUIRED, check


def fixture_repo(tmp_path):
    for relative in REQUIRED:
        p = tmp_path / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('test-only content\n', encoding='utf-8')
    return tmp_path


def test_public_source_tree_passes_offline_preflight():
    result = check()
    assert result['preflight'] == 'passed'
    assert result['publication'] == 'NOT performed'
    assert result['text_files_scanned'] > 25


def test_clean_tree_is_allowed(tmp_path):
    assert check(fixture_repo(tmp_path))['preflight'] == 'passed'


@pytest.mark.parametrize('relative', (
    '.env', 'nested/.env.production', 'secrets/private.key',
    'secrets/id_ed25519', 'generated/state.db', 'sessions/local-token', 'vault/agentflow.enc',
))
def test_private_files_are_blocked_even_in_nested_folders(tmp_path, relative):
    root = fixture_repo(tmp_path)
    file = root / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text('placeholder', encoding='utf-8')
    with pytest.raises(RuntimeError, match='private file'):
        check(root)


def test_historical_validation_logs_are_scanned(tmp_path):
    root = fixture_repo(tmp_path)
    logs = root / 'validation' / 'old.log'
    logs.parent.mkdir()
    # Assemble a fake token so no test source contains a real-looking PAT.
    logs.write_text('token=' + 'gh' + 'p_' + 'A' * 40, encoding='utf-8')
    with pytest.raises(RuntimeError, match='validation/old.log: possible github credential'):
        check(root)


def test_private_keys_are_blocked_without_printing_contents(tmp_path):
    root = fixture_repo(tmp_path)
    secret = root / 'notes.txt'
    secret.write_text('-----BEGIN OPENSSH ' + 'PRIVATE KEY-----\nFAKE', encoding='utf-8')
    with pytest.raises(RuntimeError, match='possible private key') as caught:
        check(root)
    assert 'FAKE' not in str(caught.value)


def test_symlinks_are_blocked(tmp_path):
    root = fixture_repo(tmp_path)
    destination = root / 'notes.md'
    destination.write_text('safe\n')
    link = root / 'shortcut.md'
    try:
        link.symlink_to(destination)
    except (NotImplementedError, OSError):
        pytest.skip('host cannot create symlinks')
    with pytest.raises(RuntimeError, match='symlinked file'):
        check(root)


def test_release_workflow_does_not_gain_publishing(tmp_path):
    root = fixture_repo(tmp_path)
    workflow = root / '.github/workflows/release.yml'
    workflow.write_text('steps:\n  - run: python -m twine upload dist/*\n')
    with pytest.raises(RuntimeError, match='publishing-related marker'):
        check(root)


def test_example_env_is_safe(tmp_path):
    root = fixture_repo(tmp_path)
    (root / '.env.example').write_text('TOKEN=REPLACE_ME\n')
    assert check(root)['preflight'] == 'passed'


def test_desktop_smoke_works_without_manual_pythonpath(monkeypatch):
    from agentflow_runtime.desktop import self_test
    monkeypatch.delenv('PYTHONPATH', raising=False)
    output = self_test()
    assert output['self_test'] == 'PASSED'
    assert output['echo'] == 'succeeded'


def test_sensitive_local_artifacts_are_gitignored():
    from tools.prepare_github import ROOT
    contents = (ROOT / '.gitignore').read_text(encoding='utf-8')
    for expected in ('.env.*', 'local-token', '*.sqlite', '*.pem', '*.key', '*.enc'):
        assert expected in contents
    assert '!.env.example' in contents
