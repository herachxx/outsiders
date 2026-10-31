"""Regressions for the teammate merge and clean/public startup."""
from pathlib import Path
from fastapi.testclient import TestClient
from app.api import create_app
from app.core import TriageService
from app.rules import RuleIndex
from app.schemas import TriageRequest
from app.priority import route
from scripts.bootstrap_check import needs_ml


def payload(text, kind='report', **other):
    return {'kind': kind, 'messages': [{'role':'player', 'text':text}], **other}


def test_payment_overrides_generic_account_wording():
    response=TriageService(RuleIndex([])).triage(payload('С аккаунта оплатил Grand Coins, монеты не пришли'))
    assert response['category']=='report.payment' and response['needs_human']
    assert response['priority']=='p0'


def test_technical_error_stays_help():
    response=TriageService(RuleIndex([])).triage(payload('Игра вылетает при запуске, что делать?'))
    assert response['category']=='report.help'


def test_complaint_never_auto_closes_including_invalid():
    for category in ('complaint.invalid','report.complaint','complaint.cheat','complaint.admin'):
        assert route(category,'Нужно проверить').needs_human


def test_misleading_claim_does_not_create_unrequested_rule_citation():
    data={'rules':[{'id':11,'category':'rules','points':[{'ref':'5.2','text':'Запрещено использование читов.'}]}]}
    result=TriageService(RuleIndex.from_data(data)).triage(payload('Игрок использовал чит',kind='complaint',rule_refs_raw='2.1'))
    assert result['draft_reply']['cited']==[]


def test_no_weights_do_not_require_optional_ml(tmp_path):
    assert not needs_ml(tmp_path)
    model_dir=tmp_path/'private'/'models';model_dir.mkdir(parents=True)
    (model_dir/'category_model.cbm').write_bytes(b'test')
    assert not needs_ml(tmp_path)
    (model_dir/'classifier_meta.joblib').write_bytes(b'test')
    assert needs_ml(tmp_path)


def test_empty_public_checkout_is_usable_safely(tmp_path,monkeypatch):
    monkeypatch.setenv('GRAND_DB_PATH',str(tmp_path/'test.db'))
    monkeypatch.delenv('GRAND_RULES_PATH',raising=False)
    monkeypatch.setenv('GRAND_LOCAL_LLM','0')
    with TestClient(create_app()) as client:
        assert client.get('/').status_code==200
        created=client.post('/support/tickets',json={'topic':'technical','request':payload('Игра вылетает при запуске')})
        assert created.status_code==201
        ticket=created.json();assert ticket['result']['needs_human']
        assert ticket['result']['confidence']==0
        assert ticket['result']['draft_reply']['cited']==[]
        result=client.get('/support/tickets/'+ticket['id'],headers={'X-Ticket-Token':ticket['access_token']})
        assert result.status_code==200
