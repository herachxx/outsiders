"""Regression tests for the clean operator layout and real language switcher."""
from pathlib import Path
from fastapi.testclient import TestClient
from app.api import create_app
from app.core import TriageService
from app.rules import RuleIndex
from test_core import RULES

BASE = Path(__file__).resolve().parents[1] / 'app' / 'ui'


def test_player_languages_are_selectable_and_have_localized_labels():
    page = (BASE / 'index.html').read_text(encoding='utf-8')
    translations = (BASE / 'i18n.js').read_text(encoding='utf-8')
    assert '<select id="language"' in page
    for lang in ('ru', 'kk', 'uz'):
        assert f'value="{lang}"' in page
    assert "window.GrandI18n={tr,apply,set" in translations
    assert 'Қандай көмек қажет?' in translations
    assert 'Qanday yordam kerak?' in translations
    assert 'RU / KZ / UZ' not in page


def test_operator_panel_is_one_ticket_view_with_visible_assistant_state():
    html = (BASE / 'admin.html').read_text(encoding='utf-8')
    js = (BASE / 'admin.js').read_text(encoding='utf-8')
    for ident in ('status-chip', 'open-help', 'selftest', 'next-step', 'send', 'check', 'save', 'escalate', 'to-player', 'queue-empty'):
        assert f'id="{ident}"' in html
    assert 'role="tablist"' not in html
    assert 'innerHTML' not in js
    assert "'/admin/api/selftest'" in js and "'/api/status'" in js


def test_locally_served_player_bundle_contains_i18n_and_css():
    with TestClient(create_app(TriageService(RuleIndex([])))) as client:
        for file in ('i18n.js','player.js','player.css','admin.js','admin.css','style.css'):
            resp=client.get('/ui/'+file)
            assert resp.status_code == 200
            assert resp.content


def test_player_page_does_not_claim_official_submission():
    html = (BASE / 'index.html').read_text(encoding='utf-8')
    js = (BASE / 'player.js').read_text(encoding='utf-8')
    assert 'Независимый конкурсный прототип. Неофициальный канал поддержки.' not in html
    assert 'Официальная поддержка' in html  # link for human follow-up
    assert 'В официальную поддержку Grand Mobile ничего не отправлено' not in js
    assert "'/support/tickets'" in js


def test_status_endpoints_and_analysis_meta(tmp_path, monkeypatch):
    monkeypatch.setenv('GRAND_DB_PATH', str(tmp_path / 's.sqlite3'))
    monkeypatch.setenv('GRAND_ADMIN_PASSWORD', 'test-password-secure-123')
    monkeypatch.setenv('GRAND_SESSION_SECRET', 'test-secret-is-longer-than-32-characters')
    with TestClient(create_app(TriageService(RuleIndex.from_data(RULES)))) as client:
        status = client.get('/api/status').json()
        assert status['rules_loaded'] and status['mode'] == 'rules' and status['rules_count'] > 0
        assert client.get('/admin/api/status').status_code == 401
        assert client.post('/admin/api/selftest').status_code in (401, 403)
        client.post('/admin/api/login', json={'password': 'test-password-secure-123'})
        csrf = client.get('/admin/api/session').json()['csrf']
        out = client.post('/admin/api/selftest', headers={'X-CSRF-Token': csrf}, json={}).json()
        assert len(out['results']) == 4 and all('category' in r for r in out['results'])
        assert client.get('/admin/api/tickets').json()['items'] == []
        ticket = client.post('/admin/api/tickets', headers={'X-CSRF-Token': csrf}, json={'request': {
            'kind': 'report', 'messages': [{'role': 'player', 'text': 'Где магазин?'}]}}).json()
        assert {'ms', 'mode', 'rules_version', 'analysed_at'} <= set(ticket['result']['meta'])


def test_manual_mode_is_reported_without_rules():
    with TestClient(create_app(TriageService(RuleIndex([])))) as client:
        status = client.get('/api/status').json()
        assert status['rules_loaded'] is False and status['mode'] == 'manual'
