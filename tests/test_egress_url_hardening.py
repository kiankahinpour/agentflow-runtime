"""Offline tests for fail-closed HTTPS request-target parsing."""
import socket
import pytest
from agentflow_runtime.secrets_policy import EgressPolicy

@pytest.mark.parametrize('host', [
    '-bad.example', 'bad-.example', 'bad..example', 'bad_example.org',
    'a'*64 + '.example', 'example.', 'UPPER.example',
])
def test_invalid_dns_labels_refused(host):
    with pytest.raises(ValueError, match='hostname'):
        EgressPolicy([host])

@pytest.mark.parametrize('url', [
    'https://api.example.org/a b',
    'https://api.example.org/a\\b',
    'https://api.example.org/a\x7fb',
    'https://api.example.org/é',
    'https://api.example.org:bad/',
    'https://api.example.org:99999/',
    'https://api.example.org/a\r\nInjected:yes',
])
def test_unsafe_url_rejected_before_dns(monkeypatch, url):
    def forbidden(*args, **kwargs):
        raise AssertionError('DNS must not be called for invalid URL')
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    with pytest.raises(PermissionError):
        EgressPolicy(['api.example.org']).resolve(url)

def test_safe_encoded_path_and_public_resolution(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))])
    assert EgressPolicy(['api.example.org']).resolve(
        'https://api.example.org/a%20b?x=%C3%A9') == (
        'api.example.org', '8.8.8.8', '/a%20b', 'x=%C3%A9')
