import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.core import TriageService
from app.rules import RuleIndex

RULES = {'rules': [{'id': 30, 'category': 'Общие правила', 'points': [
    {'ref': '2.1', 'text': 'Запрещены оскорбления игроков.'}]}]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('GRAND_ADMIN_PASSWORD', 'super-long-test-password')
    monkeypatch.setenv('GRAND_SESSION_SECRET', 'a-very-long-test-secret-that-cannot-be-guessed')
    with TestClient(create_app(TriageService(RuleIndex.from_data(RULES)))) as c:
        yield c


def test_send_button_flow_verifies_then_resolves_and_records_it(client):
    text = {'request': {'kind': 'report', 'messages': [{'role': 'player', 'text': 'Где находится автошкола?'}]}}
    ticket = client.post('/support/tickets', json=text).json()
    csrf = client.post('/admin/api/login', json={'password': 'super-long-test-password'}).json()['csrf']
    headers, base = {'X-CSRF-Token': csrf}, '/admin/api/tickets/' + ticket['id']
    item = client.get(base).json()
    verified = client.post(base + '/verify', headers=headers, json={'version': item['version']}).json()
    assert verified['approved'] is True
    step = client.post(base + '/status', headers=headers, json={'version': verified['ticket']['version'], 'status': 'in_review'}).json()
    done = client.post(base + '/status', headers=headers, json={'version': step['version'], 'status': 'resolved', 'note': 'отправлено'}).json()
    assert done['status'] == 'resolved'
    actions = [event['action'] for event in client.get(base + '/audit').json()['events']]
    assert actions.count('status_changed') == 2 and 'draft_verified' in actions and actions[-1] == 'created'   # newest first


def test_admin_page_has_the_three_buttons_from_the_regulation(client):
    client.post('/admin/api/login', json={'password': 'super-long-test-password'})
    page = client.get('/admin').text
    assert 'id="send"' in page and 'Отправить' in page            # send
    assert 'id="save"' in page and 'Сохранить' in page            # edit
    assert 'id="escalate"' in page and 'Передать на проверку' in page   # escalate
