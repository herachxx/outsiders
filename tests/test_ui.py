from fastapi.testclient import TestClient
from app.api import create_app
from app.core import TriageService
from app.rules import RuleIndex
from test_core import RULES


def test_ui_assets_are_served_without_external_resources():
    with TestClient(create_app(TriageService(RuleIndex.from_data(RULES)))) as client:
        page = client.get('/')
        assert page.status_code == 200
        assert 'Рабочая очередь' in page.text
        assert 'https://' not in page.text
        assert client.get('/ui/app.js').status_code == 200
        assert client.get('/ui/style.css').status_code == 200


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


def test_ui_has_send_and_export_controls_gated_by_the_server_check():
    with TestClient(create_app(TriageService(RuleIndex.from_data(RULES)))) as client:
        page, script = client.get('/').text, client.get('/ui/app.js').text
        assert 'id="send"' in page and 'disabled>Отправить' in page and 'id="export"' in page
        assert "$('send').disabled=!result.approved" in script      # enabled only after a passed check
        assert "$('send').disabled=true" in script                    # any edit or new selection locks it again
        assert 'grand-edits.jsonl' in script and "action:i.sent?'sent'" in script
