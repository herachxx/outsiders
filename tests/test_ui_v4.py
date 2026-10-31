"""Regression tests for the clean operator layout and real language switcher."""
from pathlib import Path
from fastapi.testclient import TestClient
from app.api import create_app
from app.core import TriageService
from app.rules import RuleIndex

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


def test_operator_details_are_split_into_accessible_tabs():
    html = (BASE / 'admin.html').read_text(encoding='utf-8')
    js = (BASE / 'app.js').read_text(encoding='utf-8')
    for tab in ('summary', 'reply', 'details', 'history'):
        assert f'id="tab-{tab}"' in html
        assert f'id="panel-{tab}"' in html
    for removed in ('id="mode"','id="health"','id="notice"', 'Ручной режим · нет правил', 'Серверная очередь'):
        assert removed not in html
    assert "const region=$('toast-region')" in js
    assert "dismiss.addEventListener('click'" in js
    assert 'function switchTab(name)' in js


def test_locally_served_player_bundle_contains_i18n_and_css():
    with TestClient(create_app(TriageService(RuleIndex([])))) as client:
        for file in ('i18n.js','player.js','player.css','app.js','style.css'):
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
