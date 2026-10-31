from html.parser import HTMLParser
from pathlib import Path
from fastapi.testclient import TestClient
from app.api import create_app
from app.core import TriageService
from app.rules import RuleIndex


def test_assistant_status_reports_real_capabilities_without_paths():
    empty=TriageService(RuleIndex([]))
    with TestClient(create_app(empty)) as client:
        state=client.get('/support/status').json()
        assert not state['ready'] and not state['rules_loaded']
        assert state['classification']=='rules' and state['drafts']=='templates'
    ready=TriageService(RuleIndex.from_data({'rules':[{'id':1,'category':'test','points':[{'ref':'1.1','text':'test'}]}]}),classifier=object())
    with TestClient(create_app(ready)) as client:
        state=client.get('/support/status').json()
        assert state['ready'] and state['classification']=='model'
        assert 'path' not in str(state)


class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.links=[];self.targets=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.append(attrs['id'])
        if tag=='a':self.links.append(attrs.get('href'))
        if tag=='label' and 'for' in attrs:self.targets.append(attrs['for'])


def test_pages_have_return_navigation_unique_ids_and_valid_labels():
    root=Path(__file__).resolve().parents[1]/'app/ui'
    for name,target in [('index.html','/admin'),('admin.html','/'),('setup.html','/')]:
        page=Page();page.feed((root/name).read_text(encoding='utf-8'))
        assert target in page.links
        assert len(page.ids)==len(set(page.ids)), name
        assert set(page.targets)<=set(page.ids), name


def test_new_assets_ship_locally():
    with TestClient(create_app(TriageService(RuleIndex([])))) as client:
        for name in ['workspace.css','experience.css','service-status.js']:
            result=client.get('/ui/'+name)
            assert result.status_code==200 and result.content
