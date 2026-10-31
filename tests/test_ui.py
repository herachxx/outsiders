from fastapi.testclient import TestClient
from app.api import create_app
from app.core import TriageService
from app.rules import RuleIndex
from test_core import RULES


def test_ui_assets_are_served_without_external_resources(monkeypatch):
    monkeypatch.setenv("GRAND_ADMIN_PASSWORD", "test-password-secure-123")
    monkeypatch.setenv("GRAND_SESSION_SECRET", "test-secret-is-longer-than-32-characters")
    with TestClient(create_app(TriageService(RuleIndex.from_data(RULES)))) as client:
        page = client.get('/')
        assert page.status_code == 200
        assert 'ТВОЯ ИГРА.' in page.text
        assert 'Платежи и покупки' in page.text
        assert client.get('/admin', follow_redirects=False).status_code == 303
        assert 'Вход в панель' in client.get('/admin/login').text
        assert 'Вернуться на страницу игрока' in client.get('/admin/login').text
        assert client.post('/admin/api/login', json={'password':'test-password-secure-123'}).status_code == 200
        admin = client.get('/admin').text
        assert 'Ответ игроку' in admin and 'Что понял помощник' in admin
        assert 'id="toasts"' in admin and 'id="status-chip"' in admin
        assert 'href="/"' in admin and 'Страница игрока' in admin
        assert 'Панель оператора' in page.text and 'href="/admin"' in page.text
        assert 'src="https://' not in page.text
        assert client.get('/ui/admin.js').status_code == 200
        assert client.get('/ui/admin.css').status_code == 200
        assert client.get('/ui/player.css').status_code == 200
        assert client.get('/ui/player.js').status_code == 200
        assert client.get('/ui/i18n.js').status_code == 200
        assert client.get('/ui/hero-city.svg').status_code == 200


def test_edited_draft_requires_server_gate():
    with TestClient(create_app(TriageService(RuleIndex.from_data(RULES)))) as client:
        request = {'kind': 'report', 'messages': [{'role': 'player', 'text': 'Где магазин?'}]}
        result = client.post('/triage?format=internal', json=request).json()
        payload = {'request': request, 'draft': result['draft_reply']}
        assert client.post('/draft/check', json=payload).json()['approved'] is True
        payload['draft']['text'] = 'Вернём деньги'
        checked = client.post('/draft/check', json=payload).json()
        assert checked['approved'] is False
        assert checked['draft']['cited'] == []


def test_ui_is_available_but_processing_fails_without_rules():
    with TestClient(create_app(TriageService(RuleIndex([])))) as client:
        assert client.get('/').status_code == 200
        assert client.post('/triage', json={'kind': 'report', 'messages': [{'role': 'player', 'text': 'Помогите'}]}).status_code == 503
