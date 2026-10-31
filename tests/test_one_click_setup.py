"""Fresh install, one launcher per OS, and browser-only admin onboarding."""
from __future__ import annotations

import os
from pathlib import Path
from fastapi.testclient import TestClient
from scripts.launch import prepare
from app.api import create_app
from app.support import auth


def test_first_run_is_browser_setup(tmp_path, monkeypatch):
    for key in ('GRAND_OPERATOR_CONFIG', 'GRAND_DB_PATH', 'GRAND_UPLOAD_DIR', 'GRAND_RULES_PATH', 'GRAND_ADMIN_PASSWORD', 'GRAND_SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    assert prepare(root=tmp_path) is None
    assert not (tmp_path / 'data' / 'operator.json').exists()
    with TestClient(create_app()) as client:
        response = client.get('/admin', follow_redirects=False)
        assert response.status_code == 303
        assert response.headers['location'] == '/admin/setup'
        assert client.get('/admin/login', follow_redirects=False).headers['location'] == '/admin/setup'
        assert client.get('/admin/setup').status_code == 200
        bad = client.post('/admin/api/setup', json={'password':'short'})
        assert bad.status_code == 422
        assert client.post('/admin/api/setup', json={'password':'long-safe-password-1234'}, headers={'Origin':'http://evil.local'}).status_code == 403
        result = client.post('/admin/api/setup', json={'password':'long-safe-password-1234'})
        assert result.status_code == 201, result.text
        assert auth.configured()
        assert client.get('/admin').status_code == 200
        assert client.get('/admin/api/session').status_code == 200
        assert client.get('/admin/setup', follow_redirects=False).status_code == 303
        assert client.post('/admin/api/setup',json={'password':'another-long-secret'}).status_code == 409
    record = (tmp_path/'data'/'operator.json').read_text()
    assert 'long-safe-password-1234' not in record
    assert prepare(root=tmp_path) is not None
    with TestClient(create_app()) as client:
        assert client.get('/admin', follow_redirects=False).headers['location']=='/admin/login'
        assert client.post('/admin/api/login',json={'password':'long-safe-password-1234'}).status_code == 200
    # prepare() modifies process-wide environment variables intentionally; isolate tests.
    for key in ('GRAND_OPERATOR_CONFIG', 'GRAND_DB_PATH', 'GRAND_UPLOAD_DIR', 'GRAND_RULES_PATH'):
        os.environ.pop(key,None)


def test_windows_batch_is_ascii_crlf_with_one_entry():
    root = Path(__file__).resolve().parents[1]
    bat = (root / 'START_WINDOWS.bat').read_bytes()
    assert bat.decode('ascii')
    assert b'\r\n' in bat and bat.count(b'\n') == bat.count(b'\r\n')
    assert b'scripts.windows_bootstrap' in bat
    assert len(list(root.glob('*.bat'))) == 1
    assert len(list(root.glob('*.sh'))) == 1


def test_windows_bootstrap_probes_venv_not_system(tmp_path, monkeypatch):
    from scripts import windows_bootstrap
    python = tmp_path/'.venv'/'bin'/'python'
    python.parent.mkdir(parents=True)
    python.write_text('stub')
    (tmp_path/'pyproject.toml').write_text('[project]\ndependencies=["fastapi>=0.115"]\n[project.optional-dependencies]\nml=[]\n')
    calls=[]
    def runner(command, **kwargs):
        calls.append(command)
        return [1,0,0][len(calls)-1]
    monkeypatch.setattr(windows_bootstrap.subprocess,'call',runner)
    monkeypatch.setattr(windows_bootstrap,'_venv_python',lambda root: python)
    monkeypatch.setattr(windows_bootstrap,'os',os)
    assert windows_bootstrap.bootstrap(root=tmp_path,run=False) == 0
    assert calls[0][:3]==[str(python),'-m','scripts.bootstrap_check']
    assert calls[1][:4]==[str(python),'-m','pip','install']
    assert calls[2][:3]==[str(python),'-m','scripts.bootstrap_check']
