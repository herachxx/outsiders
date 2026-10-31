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
    for tab in ('case', 'reply', 'files', 'history'):
        assert f'id="tab-{tab}"' in html and f'id="panel-{tab}"' in html
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


def test_every_element_the_operator_script_looks_up_exists_in_the_page():
    import re
    html = (BASE / 'admin.html').read_text(encoding='utf-8')
    js = (BASE / 'admin.js').read_text(encoding='utf-8')
    wanted = set(re.findall(r"\$\('#([A-Za-z0-9_-]+)'\)", js))
    missing = sorted(i for i in wanted if f'id="{i}"' not in html)
    assert not missing, missing


def test_operator_can_load_rules_from_the_panel(tmp_path, monkeypatch):
    monkeypatch.setenv('GRAND_DB_PATH', str(tmp_path / 'r.sqlite3'))
    monkeypatch.setenv('GRAND_ADMIN_PASSWORD', 'test-password-secure-123')
    monkeypatch.setenv('GRAND_SESSION_SECRET', 'test-secret-is-longer-than-32-characters')
    with TestClient(create_app(TriageService(RuleIndex([])))) as client:
        assert client.get('/api/status').json()['rules_loaded'] is False
        client.post('/admin/api/login', json={'password': 'test-password-secure-123'})
        headers = {'X-CSRF-Token': client.get('/admin/api/session').json()['csrf']}
        bad = client.post('/admin/api/rules', headers=headers, json={'nope': 1})
        assert bad.status_code == 422 and 'rules.json' in bad.json()['detail']
        assert client.post('/admin/api/rules', json=RULES).status_code in (401, 403)
        ok = client.post('/admin/api/rules', headers=headers, json=RULES)
        assert ok.status_code == 200 and ok.json()['rules_loaded'] is True
        assert (tmp_path / 'rules.json').is_file()
        assert client.get('/api/status').json()['mode'] == 'rules'


def test_demo_rules_are_labelled_and_launcher_falls_back_to_them(tmp_path, monkeypatch):
    import json, os
    from scripts.launch import prepare
    demo = json.loads((BASE.parent / 'demo_rules.json').read_text(encoding='utf-8'))
    assert all(section['category'].startswith('ДЕМО') for section in demo['rules'])
    for key in ('GRAND_RULES_PATH', 'GRAND_DB_PATH', 'GRAND_UPLOAD_DIR', 'GRAND_OPERATOR_CONFIG'):
        monkeypatch.delenv(key, raising=False)
    prepare(root=tmp_path, password='correct horse battery staple')
    assert os.environ['GRAND_RULES_PATH'].endswith('demo_rules.json')
    assert (tmp_path / 'data' / 'support.sqlite3').is_file()
    from app.core import TriageService
    from app.rules import RuleIndex
    from app.support.routes import describe_service
    info = describe_service(TriageService(RuleIndex.from_data(demo)))
    assert info['demo'] is True and info['mode'] == 'demo'
    assert describe_service(TriageService(RuleIndex.from_data(RULES)))['demo'] is False
    monkeypatch.undo()
