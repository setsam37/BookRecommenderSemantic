"""Azure bootstrap checks use no credentials or cloud services."""
import importlib.util
from pathlib import Path
from urllib.error import HTTPError

import pytest


def load_bootstrap():
    path = Path(__file__).resolve().parents[1] / 'deploy' / 'azure_bootstrap.py'
    assert path.exists(), 'Azure bootstrap has not been implemented'
    spec = importlib.util.spec_from_file_location('azure_bootstrap', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def config():
    return {'codeCommit': 'a' * 40, 'vaultUri': 'https://demo.vault.azure.net/',
            'secretName': 'openai-api-key', 'clientId': '11111111-1111-1111-1111-111111111111'}


def test_retries_role_propagation_and_reads_only_selected_secret(config):
    bootstrap = load_bootstrap()
    calls, sleeps = [], []

    def request_json(request):
        calls.append(request)
        if '169.254.169.254' in request.full_url:
            return {'access_token': 'test-managed-token'}
        if len(calls) == 2:
            raise HTTPError(request.full_url, 403, 'role not ready', {}, None)
        return {'value': 'test-replacement-key'}

    key = bootstrap.fetch_secret(config, request_json=request_json, sleep=sleeps.append, attempts=2)
    assert key == 'test-replacement-key'
    assert sleeps == [10]
    assert calls[-1].full_url == 'https://demo.vault.azure.net/secrets/openai-api-key?api-version=7.4'
    assert calls[-1].get_header('Authorization') == 'Bearer test-managed-token'


def test_failed_secret_retrieval_is_bounded_and_does_not_create_env(config, tmp_path):
    bootstrap = load_bootstrap()
    def request_json(request):
        raise HTTPError(request.full_url, 403, 'denied', {}, None)

    sleeps = []
    with pytest.raises(RuntimeError, match='Secret retrieval failed'):
        bootstrap.fetch_secret(config, request_json=request_json, sleep=sleeps.append, attempts=2)
    assert sleeps == [10]
    assert not (tmp_path / '.env').exists()


@pytest.mark.parametrize('value', ['', 'bad\nOTHER_SETTING=value', 'bad\rvalue', None])
def test_invalid_key_preserves_existing_runtime_file(tmp_path, value):
    bootstrap = load_bootstrap()
    target = tmp_path / '.env'
    target.write_text('existing configuration')
    with pytest.raises(ValueError):
        bootstrap.write_runtime_env(value, target)
    assert target.read_text() == 'existing configuration'


def test_runtime_key_file_contains_required_settings(tmp_path):
    bootstrap = load_bootstrap()
    target = tmp_path / '.env'
    bootstrap.write_runtime_env('test-key', target)
    assert target.read_text() == 'OPENAI_API_KEY=test-key\nOPENAI_EMBEDDING_MODEL=text-embedding-3-small\n'


@pytest.mark.parametrize('field,value', [
    ('vaultUri', 'http://demo.vault.azure.net/'),
    ('vaultUri', 'https://example.com/'),
    ('codeCommit', 'a; echo bad'),
    ('secretName', '../another-secret'),
    ('clientId', 'not-an-identity'),
])
def test_invalid_deployment_config_rejected_before_network(config, field, value):
    bootstrap = load_bootstrap()
    config[field] = value
    with pytest.raises(ValueError):
        bootstrap.validate_config(config)
