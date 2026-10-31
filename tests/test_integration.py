import pytest

@pytest.fixture(autouse=True)
def _explicit_dev_integration(monkeypatch):
    monkeypatch.setenv('GRAND_ALLOW_LOCAL_INTEGRATION','1')

from fastapi.testclient import TestClient

from app.api import create_app
from app.core import TriageService
from app.rules import RuleIndex

RULES = {"rules": [{"id": 30, "category": "Общие правила", "points": [
    {"ref": "2.1", "text": "Запрещены оскорбления игроков."},
    {"ref": "5.2", "text": "Запрещено использовать читы."},
]}]}

RECORD = {
    'ticket_id': 'abc123', 'created_at': '2026-10-01T10:00:00', 'kind': 'complaint', 'lang': 'ru',
    'region': 'kz', 'server_lang': 'ru', 'status': 2, 'images_count': 1, 'rule_refs_raw': '5.2 оп',
    'verdict': 'approved', 'punishment': 'бан на 31 день', 'violation': '5.2 ОП',
    'messages': [{'role': 'player', 'ts': '2026-10-01T10:00:00', 'text': 'читы <url>'},
                 {'role': 'admin', 'ts': '2026-10-01T11:00:00', 'text': 'жалоба одобрена'}],
}


def client():
    return TestClient(create_app(TriageService(RuleIndex.from_data(RULES))))


def test_exported_record_is_accepted_and_outcome_fields_are_ignored():
    response = client().post('/integration/ticket', json=RECORD)
    assert response.status_code == 200
    body = response.json()
    assert body['ticket_id'] == 'abc123'
    assert body['result']['category'] == 'complaint.cheat'
    leaked = {**RECORD, 'verdict': 'rejected', 'punishment': 'x', 'violation': 'y'}
    assert client().post('/integration/ticket', json=leaked).json() == body


def test_ticket_id_is_required_and_bad_tickets_are_rejected():
    no_id = {k: v for k, v in RECORD.items() if k != 'ticket_id'}
    assert client().post('/integration/ticket', json=no_id).status_code == 422
    assert client().post('/integration/ticket', json={**RECORD, 'messages': []}).status_code == 422
    assert client().post('/integration/ticket', json={**RECORD, 'kind': 'other'}).status_code == 422


def test_api_key_is_enforced_when_configured(monkeypatch):
    monkeypatch.setenv('GRAND_API_KEY', 'secret-key')
    app_client = client()
    assert app_client.post('/integration/ticket', json=RECORD).status_code == 401
    assert app_client.post('/integration/ticket', json=RECORD, headers={'X-API-Key': 'wrong'}).status_code == 401
    assert app_client.post('/integration/ticket', json=RECORD, headers={'X-API-Key': 'secret-key'}).status_code == 200


def test_no_rules_means_unavailable():
    unavailable = TestClient(create_app(TriageService(RuleIndex([]))))
    assert unavailable.post('/integration/ticket', json=RECORD).status_code == 503
