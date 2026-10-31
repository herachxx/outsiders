"""True first-run, persistence, secure password reset and UI usability regressions."""
import os
import json
import stat
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.support import auth
from app.support.local_config import read_config, verify_password
from scripts.launch import prepare
from app.api import create_app

PW='the-long-password-I-already-created'


@pytest.fixture(autouse=True)
def _isolate_launcher_environment():
    keys=('GRAND_OPERATOR_CONFIG','GRAND_DB_PATH','GRAND_UPLOAD_DIR','GRAND_RULES_PATH')
    saved={key:os.environ.get(key) for key in keys}
    for key in keys:os.environ.pop(key,None)
    yield
    for key,value in saved.items():
        if value is None:os.environ.pop(key,None)
        else:os.environ[key]=value


def test_fresh_setup_local_password_and_persistence(tmp_path, monkeypatch):
    monkeypatch.delenv('GRAND_ADMIN_PASSWORD', raising=False)
    monkeypatch.delenv('GRAND_SESSION_SECRET', raising=False)
    config=prepare(root=tmp_path, password=PW)
    path=tmp_path/'data'/'operator.json'
    assert path.is_file()
    assert PW not in path.read_text()
    assert 'session_secret' in config and 'password' in config
    if os.name!='nt':
        assert stat.S_IMODE(path.stat().st_mode)==0o600
        assert stat.S_IMODE(path.parent.stat().st_mode)==0o700
    assert auth.configured()
    assert verify_password(PW,config['password'])
    assert not verify_password('wrong',config['password'])
    first=path.read_bytes()
    assert prepare(root=tmp_path)==config
    assert path.read_bytes()==first
    assert Path(os.environ['GRAND_DB_PATH']).parent==path.parent
    with TestClient(create_app()) as client:
        assert client.get('/admin', follow_redirects=False).status_code==303
        assert client.post('/admin/api/login',json={'password':'wrong'}).status_code==401
        assert client.post('/admin/api/login',json={'password':PW}).status_code==200
        assert client.get('/admin/api/session').status_code==200
        item=client.post('/support/tickets',json={'request':{'kind':'report','messages':[{'role':'player','text':'Не могу подключиться к серверу'}]}})
        assert item.status_code==201
        assert item.json()['result']['meta']['mode']=='demo'
        assert client.get('/admin/api/tickets').json()['total']==6
    with TestClient(create_app()) as restarted:
        assert restarted.get('/admin/api/tickets').status_code==401
        assert restarted.post('/admin/api/login',json={'password':PW}).status_code==200
        assert restarted.get('/admin/api/tickets').json()['total']==6


def test_reset_password_invalidates_session(tmp_path,monkeypatch):
    monkeypatch.delenv('GRAND_ADMIN_PASSWORD', raising=False)
    monkeypatch.delenv('GRAND_SESSION_SECRET', raising=False)
    before=prepare(root=tmp_path,password=PW)
    with TestClient(create_app()) as client:
        assert client.post('/admin/api/login',json={'password':PW}).status_code==200
        cookie=client.cookies.get(auth.COOKIE)
        after=prepare(root=tmp_path,password='a-different-long-password',reset=True)
        assert after['session_secret']!=before['session_secret']
        assert client.get('/admin/api/session').status_code==401
        assert client.post('/admin/api/login',json={'password':PW}).status_code==401
        assert client.post('/admin/api/login',json={'password':'a-different-long-password'}).status_code==200


def test_config_rejects_corruption_and_weak_password(tmp_path):
    with pytest.raises(ValueError,match='12'):
        prepare(root=tmp_path,password='abc')
    assert not (tmp_path/'data'/'operator.json').exists()
    (tmp_path/'data'/'operator.json').write_text('{broken json',encoding='utf-8')
    with pytest.raises(RuntimeError,match='повреждён'):
        prepare(root=tmp_path,password=PW)


def test_player_and_admin_have_interactive_empty_queue_assets(tmp_path,monkeypatch):
    monkeypatch.setenv('GRAND_DB_PATH',str(tmp_path/'empty.sqlite3'))
    monkeypatch.setenv('GRAND_ADMIN_PASSWORD',PW)
    monkeypatch.setenv('GRAND_SESSION_SECRET','this-is-a-long-dev-secret-test-only-1234567890')
    monkeypatch.delenv('GRAND_OPERATOR_CONFIG',raising=False)
    with TestClient(create_app()) as client:
        page=client.get('/ui/admin.html').text
        js=client.get('/ui/admin.js').text
        assert 'id="empty-new"' in page and 'id="new-ticket"' in page
        assert "$('#empty-new').addEventListener('click', openNew)" in js
        assert 'id="queue-empty"' in page
        assert client.get('/ui/player.js').status_code==200
        assert 'service-status' not in client.get('/ui/player.js').text
        assert client.get('/ui/i18n.js').status_code == 200


def test_unconfigured_integration_is_not_public(tmp_path,monkeypatch):
    monkeypatch.setenv('GRAND_DB_PATH',str(tmp_path/'empty.db'))
    monkeypatch.delenv('GRAND_API_KEY',raising=False)
    monkeypatch.delenv('GRAND_ALLOW_LOCAL_INTEGRATION',raising=False)
    with TestClient(create_app()) as client:
        res=client.post('/integration/ticket',json={'ticket_id':'X1'})
        assert res.status_code==503


def test_selected_topic_preserved_in_manual_mode(tmp_path,monkeypatch):
    monkeypatch.setenv('GRAND_DB_PATH',str(tmp_path/'topics.sqlite3'))
    monkeypatch.delenv('GRAND_RULES_PATH',raising=False)
    with TestClient(create_app()) as client:
        response=client.post('/support/tickets',json={'topic':'payment','request':{'kind':'report','messages':[{'role':'player','text':'Оплатил Grand Coins, не пришли'}]}})
        assert response.status_code==201
        result=response.json()['result']
        assert result['category']=='report.payment'
        assert result['confidence']==0
        assert result['needs_human'] is True
        assert 'topic_selected_by_player' in result['reasons']
        invalid=client.post('/support/tickets',json={'topic':'script', 'request':{'kind':'report','messages':[{'role':'player','text':'hi'}]}})
        assert invalid.status_code==422
