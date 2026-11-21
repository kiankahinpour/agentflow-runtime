"""Checks for bounded API requests and non-publishing release workflow."""
import json
from pathlib import Path
import runpy

import pytest
from fastapi.testclient import TestClient

from agentflow_runtime import Store
from agentflow_runtime.api import MAX_API_BODY_BYTES, create_app
from agentflow_runtime._version import __version__

TOKEN = 'local-test-token-for-public-beta-123'
ROOT = Path(__file__).resolve().parents[1]


def client(tmp_path):
    store = Store(tmp_path / 'api.db')
    return TestClient(create_app(store, TOKEN)), store


def auth():
    return {'Authorization': 'Bearer ' + TOKEN}


def test_anonymous_post_denied_before_processing_body(tmp_path):
    c, store = client(tmp_path)
    response = c.post('/api/jobs', content=b'x' * (MAX_API_BODY_BYTES + 8))
    assert response.status_code == 401
    assert response.headers['Cache-Control'] == 'no-store'
    assert store.list() == []


def test_authenticated_oversized_content_length_rejected(tmp_path):
    c, store = client(tmp_path)
    response = c.post('/api/jobs', headers=auth(), content=b'x' * (MAX_API_BODY_BYTES + 1))
    assert response.status_code == 413
    assert store.list() == []


def test_authenticated_oversized_stream_without_content_length_rejected(tmp_path):
    c, store = client(tmp_path)
    def chunks():
        yield b'{' + b' ' * (MAX_API_BODY_BYTES // 2)
        yield b' ' * (MAX_API_BODY_BYTES // 2) + b'}'
    response = c.post('/api/jobs', headers=auth(), content=chunks())
    assert response.status_code == 413
    assert store.list() == []


def test_normal_authenticated_body_still_accepted(tmp_path):
    c, store = client(tmp_path)
    response = c.post('/api/jobs', headers=auth(), json={'prompt': 'public beta smoke'})
    assert response.status_code == 201
    assert store.get(response.json()['id'])['prompt'] == 'public beta smoke'


def test_api_reports_canonical_version(tmp_path):
    c, _ = client(tmp_path)
    assert c.get('/api/runtime', headers=auth()).json()['version'] == __version__


def test_distribution_build_version_guard(tmp_path):
    guard = runpy.run_path(str(ROOT / 'tools/check_release_version.py'))['check']
    assert guard(__version__) == __version__
    with pytest.raises(ValueError, match='version mismatch'):
        guard('0.0.1')
    with pytest.raises(ValueError, match='invalid'):
        guard('1.2.9;touch /tmp/unsafe')


def test_release_workflow_cannot_publish():
    contents = (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8')
    assert 'python tools/check_release_version.py' in contents
    assert 'REQUESTED_VERSION: ${{ inputs.version }}' in contents
    assert 'pypa/gh-action-pypi-publish' not in contents
    assert 'id-token: write' not in contents
    assert 'publish_pypi' not in contents
    assert 'upload-artifact@v4' in contents
