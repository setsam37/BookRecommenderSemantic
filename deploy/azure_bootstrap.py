"""Azure VM bootstrap. Managed-identity tokens and secrets are never printed."""
import argparse
import base64
import json
import os
import re
import subprocess
import tarfile
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlretrieve


ROOT = Path('/opt/book-recommender')


def validate_config(config):
    if not re.fullmatch(r'[a-f0-9]{40}', config.get('codeCommit', '')):
        raise ValueError('Use a full Git commit SHA.')
    uri = urlparse(config.get('vaultUri', ''))
    if (uri.scheme != 'https' or not re.fullmatch(r'[a-z0-9-]+\.vault\.azure\.net', uri.netloc)
            or uri.path not in ('', '/') or uri.query or uri.fragment):
        raise ValueError('Use an Azure public-cloud Key Vault URI.')
    if not re.fullmatch(r'[a-zA-Z0-9-]{1,127}', config.get('secretName', '')):
        raise ValueError('Invalid Key Vault secret name.')
    try:
        uuid.UUID(config.get('clientId', ''))
    except (ValueError, AttributeError) as exc:
        raise ValueError('Invalid managed identity client ID.') from exc


def _request_json(request):
    # IMDS must bypass proxy settings; this deployment also accesses Key Vault directly.
    with build_opener(ProxyHandler({})).open(request, timeout=30) as response:
        return json.load(response)


def fetch_secret(config, *, request_json=None, sleep=time.sleep, attempts=60):
    validate_config(config)
    request_json = request_json or _request_json
    query = urlencode({'api-version': '2018-02-01', 'resource': 'https://vault.azure.net',
                       'client_id': config['clientId']})
    token_url = 'http://169.254.169.254/metadata/identity/oauth2/token?' + query
    secret_url = config['vaultUri'].rstrip('/') + '/secrets/' + config['secretName'] + '?api-version=7.4'
    for attempt in range(attempts):
        try:
            token = request_json(Request(token_url, headers={'Metadata': 'true'}))['access_token']
            return request_json(Request(secret_url, headers={'Authorization': 'Bearer ' + token}))['value']
        except (HTTPError, URLError):
            # Allow Azure RBAC/identity assignment time to propagate, with bounded retries.
            if attempt + 1 < attempts:
                sleep(10)
    raise RuntimeError('Secret retrieval failed. Check identity permissions and Key Vault networking.')


def write_runtime_env(key, path):
    if not isinstance(key, str) or not key.strip() or '\n' in key or '\r' in key:
        raise ValueError('Key Vault must contain a nonempty, single-line OpenAI key.')
    path = Path(path)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.env-',
                                         delete=False, encoding='utf-8', newline='\n') as file:
            pending = Path(file.name)
            file.write('OPENAI_API_KEY=' + key.strip() + '\nOPENAI_EMBEDDING_MODEL=text-embedding-3-small\n')
        os.chmod(pending, 0o600)
        os.replace(pending, path)
    finally:
        if pending is not None and pending.exists():
            pending.unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh-key', action='store_true')
    options = parser.parse_args()
    config = json.loads(base64.b64decode((ROOT / 'config.b64').read_text()))
    validate_config(config)
    image = 'book-recommender:' + config['codeCommit']
    if not options.refresh_key:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            archive = Path(directory) / 'source.tar.gz'
            urlretrieve('https://codeload.github.com/setsam37/BookRecommenderSemantic/tar.gz/'
                        + config['codeCommit'], archive)
            source = Path(directory) / 'source'
            source.mkdir()
            with tarfile.open(archive) as tar:
                tar.extractall(source, filter='data')
            roots = list(source.iterdir())
            if len(roots) != 1 or not (roots[0] / 'Dockerfile').is_file():
                raise RuntimeError('Downloaded revision does not contain the deployment Dockerfile.')
            subprocess.run(['docker', 'build', '--tag', image, str(roots[0])], check=True)
    write_runtime_env(fetch_secret(config), ROOT / '.env')
    if options.refresh_key:
        print('Runtime key refreshed. Recreate the container to use it.')
        return
    subprocess.run(['docker', 'volume', 'create', 'book-index'], check=True)
    subprocess.run([
        'docker', 'run', '--detach', '--name', 'book-recommender', '--restart', 'unless-stopped',
        '--publish', '7860:7860', '--env-file', str(ROOT / '.env'),
        '--mount', 'source=book-index,target=/app/.cache/chroma',
        '--security-opt', 'no-new-privileges:true', '--cap-drop', 'ALL',
        '--log-opt', 'max-size=10m', '--log-opt', 'max-file=3', image,
    ], check=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Azure bootstrap failed (' + type(exc).__name__ + '). Check deployment settings; no secrets logged.')
        raise SystemExit(1)
