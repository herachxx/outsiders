import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.core import TriageService
from app.decisions import Decisions
from app.handling import decide
from app.priority import MANDATORY_HUMAN
from app.rules import RuleIndex

RULES = {"rules": [{"id": 30, "category": "Общие правила", "points": [
    {"ref": "2.1", "text": "Запрещены оскорбления игроков."}]}]}


def lane(text, kind='report', **extra):
    service = TriageService(RuleIndex.from_data(RULES))
    result = service.triage({'kind': kind, 'messages': [{'role': 'player', 'text': text}], **extra})
    return next(r.removeprefix('handling_') for r in result['reasons'] if r.startswith('handling_'))


def test_safe_question_is_auto_but_sensitive_and_appeals_are_escalated():
    assert lane('Подскажите, где находится автошкола в городе?') == 'auto'
    assert lane('Мой аккаунт взломали, не могу войти') == 'escalate'
    assert lane('Оплатил донат, деньги списаны, но ничего не пришло') == 'escalate'
    assert lane('Прошу снять варн, не согласен с наказанием', kind='complaint') == 'escalate'
    assert lane('оск родни', kind='complaint') == 'review'


def test_uncertain_language_and_low_confidence_never_go_auto():
    assert lane('?') == 'review'
    assert decide('report.question', 'p3', False, 0.3, [], MANDATORY_HUMAN) == 'review'
    assert decide('report.question', 'p3', False, 0.9, ['language_uncertain'], MANDATORY_HUMAN) == 'review'
    assert decide('report.question', 'p3', False, 0.9, ['safety_unapproved_draft'], MANDATORY_HUMAN) == 'escalate'
    assert decide('complaint.insult', 'p2', False, 0.95, [], MANDATORY_HUMAN) == 'review'


def test_decisions_track_agreement_and_keep_a_decision_when_ticket_is_resent():
    log = Decisions()
    log.propose('t1', 'complaint.insult', 'p2', 'review')
    log.propose('t2', 'complaint.cheat', 'p1', 'review')
    log.propose('t3', 'report.question', 'p3', 'auto')
    log.decide('t1', 'approved')
    log.decide('t2', 'edited', category='complaint.dm', priority='p2')
    log.propose('t1', 'complaint.other', 'p2', 'review')   # re-sent ticket must not erase the approval
    stats = log.stats()
    assert stats['proposed'] == 3 and stats['decided'] == 2
    assert stats['category_agreement'] == 0.5 and stats['priority_agreement'] == 0.5
    assert stats['by_handling']['review']['approval_rate'] == 0.5
    assert log.corrections() == [{'ticket_id': 't1', 'category': 'complaint.insult', 'priority': 'p2'},
                                 {'ticket_id': 't2', 'category': 'complaint.dm', 'priority': 'p2'}]
    with pytest.raises(KeyError):
        log.decide('missing', 'approved')
    with pytest.raises(ValueError):
        log.decide('t3', 'edited')


def test_integration_decision_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv('GRAND_DECISIONS_PATH', str(tmp_path / 'decisions.sqlite'))
    monkeypatch.setenv('GRAND_API_KEY', 'k')
    client = TestClient(create_app(TriageService(RuleIndex.from_data(RULES))))
    headers = {'X-API-Key': 'k'}
    ticket = {'ticket_id': 'a1', 'kind': 'complaint', 'messages': [{'role': 'player', 'text': 'оск родни'}]}
    body = client.post('/integration/ticket', json=ticket, headers=headers).json()
    assert body['handling'] == 'review'
    assert client.post('/integration/decision', json={'ticket_id': 'a1', 'action': 'approved'}).status_code == 401
    assert client.post('/integration/decision', headers=headers, json={'ticket_id': 'zz', 'action': 'approved'}).status_code == 404
    assert client.post('/integration/decision', headers=headers,
                       json={'ticket_id': 'a1', 'action': 'edited', 'category': 'nope'}).status_code == 422
    assert client.post('/integration/decision', headers=headers,
                       json={'ticket_id': 'a1', 'action': 'edited', 'category': 'complaint.dm'}).json()['recorded'] == 'edited'
    stats = client.get('/integration/decisions/stats', headers=headers).json()
    assert stats['decided'] == 1 and stats['category_agreement'] == 0.0


def test_decision_log_is_unavailable_when_not_configured(monkeypatch):
    monkeypatch.delenv('GRAND_DECISIONS_PATH', raising=False)
    client = TestClient(create_app(TriageService(RuleIndex.from_data(RULES))))
    assert client.post('/integration/decision', json={'ticket_id': 'a', 'action': 'approved'}).status_code == 503
