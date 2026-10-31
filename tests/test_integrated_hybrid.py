"""Integration regression: team model, safety, persistence, API and local LLM."""
import json
import os
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
import httpx
import pytest
from app.hybrid import HybridTriageService,LocalDraftGenerator,check_operator_reply,load_team_classifier
from app.rules import RuleIndex
from app.api import create_app
from app.support.store import TicketStore,Conflict
from app.schemas import TriageRequest

RULES=Path(__file__).parents[1]/'private'/'rules.json'

@pytest.fixture
def service():
    gen=LocalDraftGenerator();gen.enabled=False
    rules=(RuleIndex.from_file(str(RULES)) if RULES.exists() else RuleIndex.from_data({'rules':[{'id':30,'category':'Общие правила','points':[{'ref':'2.1','text':'Запрещено оскорблять игроков.'}]}]}))
    return HybridTriageService(rules,load_team_classifier(),gen)

@pytest.mark.parametrize('body,category,priority',[
 ('Оплатил донат, деньги списали, но Grand Coins не пришли на аккаунт','report.payment','p0'),
 ('Мой аккаунт взломали, пароль сменили','report.account','p0'),
 ('Как узнать статус моего обращения?','report.question','p3'),
 ('Игра вылетает при входе в сервер, помогите','report.help','p2'),
])
def test_categories_and_priority(service,body,category,priority):
    r=service.triage({'kind':'report','messages':[{'role':'player','text':body}]})
    assert r['category']==category
    assert r['priority']==priority
    if category in ('report.payment','report.account','report.help'):
        assert r['needs_human']


def test_automatic_close_strictly_verified_platform_question(service,tmp_path,monkeypatch):
    monkeypatch.setenv('GRAND_DB_PATH',str(tmp_path/'queue.sqlite'))
    app=create_app(service)
    with TestClient(app) as client:
        response=client.post('/support/tickets',json={'request':{
          'kind':'report','messages':[{'role':'player','text':'Как узнать статус моего обращения?'}]
        },'topic':'question'})
        assert response.status_code==201,response.text
        body=response.json()
        assert body['status']=='closed'
        assert body['result']['needs_human'] is False
        state=client.get('/support/tickets/'+body['id'],headers={'X-Ticket-Token':body['access_token']})
        assert state.status_code==200 and state.json()['status']=='closed'


def test_complaint_cannot_auto_close(service,monkeypatch,tmp_path):
    monkeypatch.setenv('GRAND_DB_PATH',str(tmp_path/'a.sqlite'))
    app=create_app(service)
    with TestClient(app) as client:
        ticket=client.post('/support/tickets',json={'request':{
            'kind':'complaint','messages':[{'role':'player','text':'Этот игрок читер, использует софт'}]
        },'topic':'complaint'}).json()
        assert ticket['status']=='new'
        assert ticket['result']['needs_human']
        with pytest.raises(Conflict):
            store=TicketStore(str(tmp_path/'a.sqlite'))
            store.auto_close_verified_faq(ticket['id'])


def test_no_auto_close_for_untrusted_generator(service):
    class LLM:
        enabled=True
        def draft(self,request,category,lang,rules):return 'Здравствуйте! Попробуйте перезапустить приложение и проверить соединение.'
    service.generator=LLM()
    request={'kind':'report','messages':[{'role':'player','text':'Как починить игру, вылетает при запуске?'}]}
    result=service.triage(request)
    assert result['needs_human']
    assert not service.can_auto_close(result,TriageRequest.model_validate(request))


def test_local_llm_rejects_cloud_endpoints(monkeypatch):
    monkeypatch.setenv('GRAND_LLM_URL','https://api.openai.com/v1')
    g=LocalDraftGenerator();assert not g.enabled


def test_local_llm_mock_response_never_fakes_citation(monkeypatch):
    monkeypatch.setenv('GRAND_LLM_URL','http://127.0.0.1:11434/v1')
    generator=LocalDraftGenerator()
    request=TriageRequest.model_validate({'kind':'report','messages':[{'role':'player','text':'Как найти работу?'}]})
    def handler(req):
        return httpx.Response(200,json={'choices':[{'message':{'content':'Попробуйте пункт 99.99 правил. Мы всё проверили.'}}]})
    generator.client.close()
    generator.client=httpx.Client(transport=httpx.MockTransport(handler))
    assert generator.draft(request,'report.question','ru',None) is None


def test_operator_cannot_approve_unverified_rule(service):
    request=TriageRequest.model_validate({'kind':'report','messages':[{'role':'player','text':'Подскажите информацию'}]})
    result,reasons=check_operator_reply({'text':'Согласно пункту 99.99 вы получите награду','lang':'ru','cited':[]},service.rules,request,'report.question','ru')
    assert 'safety_unverified_rule_numbers' in reasons


def test_private_assets_not_git_tracked():
    ignored=(Path(__file__).parents[1]/'.gitignore').read_text()
    assert 'private/' in ignored


def test_local_ollama_valid_reply_becomes_review_draft(monkeypatch,service):
    monkeypatch.setenv('GRAND_LLM_URL','http://127.0.0.1:11434/v1')
    generator=LocalDraftGenerator()
    def handler(req):
        assert req.url.path == '/v1/chat/completions'
        body=json.loads(req.content)
        assert body['model'].startswith('qwen2.5')
        assert body['temperature']==0.2 and body['max_tokens']==60
        return httpx.Response(200,json={'choices':[{'message':{'content':'Пожалуйста, уточните версию Android и на каком этапе игра вылетает.'}}]})
    generator.client.close()
    generator.client=httpx.Client(transport=httpx.MockTransport(handler))
    service.generator=generator
    req={'kind':'report','messages':[{'role':'player','text':'Где устроиться на работу механика?'}]}
    result=service.triage(req)
    assert result['needs_human']
    assert result['draft_reply']['text'].startswith('Пожалуйста')
    assert 'local_llm_draft_review_required' in result['reasons']


def test_no_llm_in_batch(service):
    from app.batch import predict_lines
    service.generator.enabled=False
    line=json.dumps({'kind':'report','messages':[{'role':'player','text':'Оплатил донат, деньги списали'}]},ensure_ascii=False)
    rows=list(predict_lines([line],service))
    assert len(rows)==1
    assert rows[0]['category']=='report.payment'
    assert rows[0]['needs_human'] is True
    assert set(rows[0]['draft_reply'])=={'text','lang','cited'}
