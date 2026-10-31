"""Full system tests for persistent queue, authorization and human gating."""
import concurrent.futures
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.core import TriageService
from app.rules import RuleIndex
from app.support.store import TicketStore, Conflict

RULES={'rules':[{'id':30,'category':'Общие правила','points':[
    {'ref':'2.1','text':'Запрещены оскорбления игроков.'},
    {'ref':'5.2','text':'Запрещено использовать читы.'}]}]}

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('GRAND_DB_PATH',str(tmp_path/'support.db'))
    monkeypatch.setenv('GRAND_ADMIN_PASSWORD','super-long-test-password')
    monkeypatch.setenv('GRAND_SESSION_SECRET','a-very-long-test-secret-that-cannot-be-guessed')
    with TestClient(create_app(TriageService(RuleIndex.from_data(RULES)))) as c:yield c

def post_player(c,text='Как начать играть?'):
    return c.post('/support/tickets',json={'request':{'kind':'report','messages':[{'role':'player','text':text}],'region':'Сервер 01'}})

def login(c):
    response=c.post('/admin/api/login',json={'password':'super-long-test-password'})
    assert response.status_code==200
    return {'X-CSRF-Token':response.json()['csrf']}

def test_public_ticket_created_persisted_private_and_admin_queue(client):
    created=post_player(client)
    assert created.status_code==201,created.text
    ticket=created.json()
    assert ticket['id'].startswith('GM-')
    assert 'access_token' in ticket and len(ticket['access_token'])>32
    assert client.get('/admin/api/tickets').status_code==401
    assert client.get('/support/tickets/'+ticket['id']).status_code==404
    assert client.get('/support/tickets/'+ticket['id'],headers={'X-Ticket-Token':'wrong'}).status_code==404
    assert client.get('/support/tickets/'+ticket['id'],headers={'X-Ticket-Token':ticket['access_token']}).status_code==200
    headers=login(client)
    queue=client.get('/admin/api/tickets').json()
    assert queue['total']==1 and queue['items'][0]['request']['messages'][0]['text']=='Как начать играть?'
    assert 'access_hash' not in str(queue)
    assert client.get('/admin').status_code==200
    assert client.get('/admin/api/tickets/'+ticket['id']+'/audit').json()['events'][0]['action']=='created'
    assert client.post('/admin/api/tickets/'+ticket['id']+'/status',json={'version':1,'status':'in_review'}).status_code==403
    assert client.post('/admin/api/tickets/'+ticket['id']+'/status',headers=headers,json={'version':1,'status':'in_review'}).status_code==200

def test_session_failure_and_logout(client):
    assert client.get('/admin',follow_redirects=False).status_code==303
    assert client.post('/admin/api/login',json={'password':'wrong'}).status_code==401
    headers=login(client)
    assert client.get('/admin/api/session').status_code==200
    assert client.post('/admin/api/logout',headers=headers).status_code==200
    assert client.get('/admin/api/session').status_code==401

def test_conflicts_verification_and_transition(client):
    ticket=post_player(client,'Где магазин?').json();headers=login(client);id=ticket['id']
    assert client.post('/admin/api/tickets/'+id+'/status',headers=headers,json={'version':1,'status':'resolved'}).status_code==409
    review=client.post('/admin/api/tickets/'+id+'/status',headers=headers,json={'version':1,'status':'in_review'})
    assert review.status_code==200
    assert client.post('/admin/api/tickets/'+id+'/status',headers=headers,json={'version':1,'status':'closed'}).status_code==409
    version=review.json()['version']
    edited=client.put('/admin/api/tickets/'+id+'/draft',headers=headers,json={'version':version,'text':'Вернём деньги за всё'})
    assert edited.status_code==200
    validation=client.post('/admin/api/tickets/'+id+'/verify',headers=headers,json={'version':edited.json()['version']})
    assert validation.status_code==200
    assert validation.json()['approved'] is False
    assert client.post('/admin/api/tickets/'+id+'/status',headers=headers,json={'version':edited.json()['version'],'status':'resolved'}).status_code==409
    # Restore rule-safe template, validate, only then allow human closure.
    item=client.get('/admin/api/tickets/'+id).json()
    repaired=client.put('/admin/api/tickets/'+id+'/draft',headers=headers,json={'version':item['version'],'text':item['result']['draft_reply']['text']})
    valid=client.post('/admin/api/tickets/'+id+'/verify',headers=headers,json={'version':repaired.json()['version']})
    assert valid.json()['approved'] is True,valid.text
    resolved=client.post('/admin/api/tickets/'+id+'/status',headers=headers,json={'version':valid.json()['ticket']['version'],'status':'resolved'})
    assert resolved.status_code==200,resolved.text
    assert client.get('/admin/api/tickets/'+id+'/audit').json()['events'][0]['action']=='status_changed'

def test_sensitive_routing_no_autoresolution(client):
    complaint=client.post('/support/tickets',json={'request':{'kind':'complaint','messages':[{'role':'player','text':'Игрок использует читы'}]}}).json()
    assert complaint['result']['needs_human'] is True
    payment=post_player(client,'Я оплатил донат, деньги списались').json()
    assert payment['result']['needs_human'] is True
    c=login(client)
    item=client.get('/admin/api/tickets/'+payment['id']).json()
    assert item['status']=='new' and item['draft_approved'] is False
    assert client.post('/admin/api/tickets/'+payment['id']+'/status',headers=c,json={'version':1,'status':'resolved'}).status_code==409

def test_duplicate_and_injection(client):
    # Identical anonymous questions may come from different players and must not be merged.
    assert post_player(client).status_code==201
    assert post_player(client).status_code==201
    assert post_player(client,"   ").status_code==422
    login(client)
    q=client.get('/admin/api/tickets',params={'q':"%' OR 1=1 --"})
    assert q.status_code==200 and q.json()['total']==0

def test_no_rules_creates_manual_queue_without_fake_confidence(tmp_path,monkeypatch):
    monkeypatch.setenv('GRAND_DB_PATH',str(tmp_path/'norules.db'))
    with TestClient(create_app(TriageService(RuleIndex([])))) as c:
        result=post_player(c,'Ошибка в игре')
        assert result.status_code==201
        info=result.json()['result']
        assert info['category']=='unclassified'
        assert info['needs_human'] is True
        assert info['confidence']==0
        assert info['reasons']==['rules_unavailable','manual_triage_required']

def test_store_concurrent_version_and_retention(tmp_path):
    store=TicketStore(str(tmp_path/'db.sqlite3'))
    req={'kind':'report','messages':[{'role':'player','text':'help'}]}
    result={'priority':'p2','draft_reply':{'text':'Hello'}}
    ticket,_=store.create(req,result)
    def edit(text):
        try:return store.edit_draft(ticket['id'],1,text,'operator')['version']
        except Conflict:return 'conflict'
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(edit,['a','b']))
    assert sorted(str(x) for x in results)==['2','conflict']
    with store.connect() as connection:
        connection.execute("UPDATE tickets SET created_at=? WHERE id=?", ("2025-01-01T00:00:00+00:00", ticket["id"]))
    assert store.purge(days=14)==1
    with pytest.raises(Exception):store.get(ticket['id'])

def test_screenshot_private_upload_with_metadata_removed(client, tmp_path):
    from PIL import Image
    import io
    from app.support.store import TicketStore
    ticket=post_player(client,'У меня ошибка графики').json()
    img=Image.new('RGB',(20,20),'white');stream=io.BytesIO();img.save(stream,format='PNG')
    endpoint=f"/support/tickets/{ticket['id']}/attachments"
    assert client.post(endpoint,files={'file':('pic.png',stream.getvalue(),'image/png')}).status_code==404
    assert client.post(endpoint,headers={'X-Ticket-Token':ticket['access_token']},files={'file':('bad.svg',b'<svg onload="alert(1)"></svg>','image/svg+xml')}).status_code==415
    uploaded=client.post(endpoint,headers={'X-Ticket-Token':ticket['access_token']},files={'file':('pic.png',stream.getvalue(),'image/png')})
    assert uploaded.status_code==201,uploaded.text
    image=uploaded.json()
    assert image['id'].startswith('ATT-')
    assert client.get(f"/admin/api/tickets/{ticket['id']}/attachments").status_code==401
    headers=login(client)
    detail=client.get(f"/admin/api/tickets/{ticket['id']}").json()
    assert detail['request']['images_count']==1
    assert detail['result']['extracted']['has_evidence'] is True
    assert detail['version']==2
    assert not detail['draft_approved']
    attachments=client.get(f"/admin/api/tickets/{ticket['id']}/attachments").json()
    assert len(attachments['items'])==1
    download=client.get(f"/admin/api/tickets/{ticket['id']}/attachments/{image['id']}")
    assert download.status_code==200 and download.headers['x-content-type-options']=='nosniff'
    assert download.headers['content-disposition'].startswith('attachment;')
    with Image.open(io.BytesIO(download.content)) as final:
        assert final.size==(20,20)

def test_payment_term_wins_over_generic_account_mention():
    service=TriageService(RuleIndex.from_data(RULES))
    result=service.triage({'kind':'report','messages':[{'role':'player','text':'Оплатил 500 Grand Coins, деньги списались, но на мой аккаунт валюта не поступила.'}]})
    assert result['category']=='report.payment'
    assert result['priority']=='p0'
    assert result['needs_human'] is True


def test_technical_report_gets_helpful_category():
    service=TriageService(RuleIndex.from_data(RULES))
    result=service.triage({'kind':'report','messages':[{'role':'player','text':'Игра вылетает сразу после загрузки. Как исправить?'}]})
    assert result['category']=='report.help'

def test_queue_filters_human_priority_and_pagination(client):
    post_player(client,'Где можно устроиться механиком?')
    post_player(client,'Оплатил донат, но деньги не пришли')
    post_player(client,'Игра вылетает после обновления')
    login(client)
    all_page=client.get('/admin/api/tickets',params={'limit':2,'offset':0}).json()
    assert all_page['total']==3 and len(all_page['items'])==2
    page2=client.get('/admin/api/tickets',params={'limit':2,'offset':2}).json()
    assert len(page2['items'])==1
    urgent=client.get('/admin/api/tickets',params={'priority':'urgent'}).json()
    assert any(t['result']['category']=='report.payment' for t in urgent['items'])
    human=client.get('/admin/api/tickets',params={'human':'true'}).json()
    assert all(t['result']['needs_human'] for t in human['items'])
    assert client.get('/admin/api/tickets',params={'priority':'bogus'}).status_code==422


def test_security_headers(client):
    response=client.get('/')
    assert response.headers['x-frame-options']=='DENY'
    assert response.headers['x-content-type-options']=='nosniff'
    assert "script-src 'self'" in response.headers['content-security-policy']


def test_selected_but_not_uploaded_files_are_not_evidence(client):
    response=client.post('/support/tickets',json={'request':{'kind':'report','images_count':4,
        'messages':[{'role':'player','text':'Ошибка графики','attachments':4}]}})
    assert response.status_code==201
    assert response.json()['result']['extracted']['has_evidence'] is False


def test_attachment_preserves_edits_invalidates_approval_and_rejects_closed(tmp_path):
    store=TicketStore(str(tmp_path/'files.db'))
    service=TriageService(RuleIndex.from_data(RULES))
    req={'kind':'report','messages':[{'role':'player','text':'Ошибка графики'}]}
    item,_=store.create(req,service.triage(req))
    item=store.edit_draft(item['id'],item['version'],'Правка оператора','operator')
    item=store.approve_draft(item['id'],item['version'],'operator')
    store.add_attachment(item['id'],'synthetic.png','image/png',1,service.triage)
    changed=store.get(item['id'])
    assert changed['draft_text']=='Правка оператора'
    assert not changed['draft_approved'] and changed['version']==item['version']+1
    with pytest.raises(Conflict):store.approve_draft(item['id'],item['version'],'operator')
    changed=store.set_status(changed['id'],changed['version'],'in_review','operator')
    changed=store.approve_draft(changed['id'],changed['version'],'operator')
    changed=store.set_status(changed['id'],changed['version'],'resolved','operator')
    with pytest.raises(Conflict):store.add_attachment(item['id'],'second.png','image/png',1,service.triage)
    assert len(store.list_attachments(item['id']))==1
