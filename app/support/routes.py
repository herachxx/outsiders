"""Authenticated operator workflow and anonymous ticket intake."""
from __future__ import annotations

import os
import io
import secrets
from pathlib import Path
from fastapi import UploadFile, File
from fastapi.responses import FileResponse
from collections import defaultdict,deque
from datetime import datetime,timezone
import time
from fastapi import APIRouter, Body, HTTPException, Request, Response, Header, Query
from pydantic import Field
from typing import Literal

from app.schemas import StrictModel, TriageRequest, TriageResponse
from app.safety import check_draft
from app.support.store import Conflict, Missing, TicketStore
from app.support.local_config import write_config
from app.support import auth


class TicketCreate(StrictModel):
    request: TriageRequest
    topic: Literal['question','complaint','technical','payment','account','idea'] | None = None


class Login(StrictModel):
    password: str = Field(min_length=1,max_length=512)


class DraftEdit(StrictModel):
    version: int = Field(ge=1)
    text: str = Field(min_length=1,max_length=20000)


class Mutation(StrictModel):
    version: int = Field(ge=1)
    status: str
    note: str = Field(default='',max_length=1000)


class Version(StrictModel):
    version: int = Field(ge=1)



def _multipart_available() -> bool:
    try:
        import python_multipart  # noqa: F401
        return True
    except ImportError:
        try:
            import multipart  # noqa: F401
            return True
        except ImportError:
            return False


SELFTEST_TEXTS = [
    ('complaint', 'Игрок Arman_Petrov оскорбил меня и мою семью в чате, скрины есть, 2.1 ОП'),
    ('complaint', 'Игрок летает и стреляет через стены, использует софт, фрапс прикрепил'),
    ('report', 'Взломали аккаунт, сменили пароль, не могу войти'),
    ('report', 'Где находится автошкола?'),
]


def describe_service(service) -> dict:
    """Plain facts about what the assistant is doing right now; no tickets, no secrets."""
    rules = getattr(service, 'rules', None)
    items = list(getattr(rules, 'rules', []) or [])
    model = getattr(service, 'classifier', None) is not None
    demo = bool(items) and all(str(item.section).startswith('ДЕМО') for item in items)
    return {'ok': True, 'rules_loaded': bool(items), 'rules_count': len(items), 'demo': demo,
            'rules_version': items[0].rules_hash[:8] if items else None,
            'model_loaded': model, 'mode': 'manual' if not items else ('demo' if demo else ('rules+model' if model else 'rules')),
            'operator_configured': auth.configured()}


def create_routes(service, store: TicketStore):
    router=APIRouter()
    rate=defaultdict(deque)
    uploads=Path(os.environ.get('GRAND_UPLOAD_DIR','data/uploads'))
    uploads.mkdir(parents=True,exist_ok=True,mode=0o700)

    def admin(request: Request,unsafe=False):return auth.ensure_admin(request,unsafe)

    def guard(ip):
        now=time.monotonic(); q=rate[ip]
        while q and q[0]<now-60:q.popleft()
        if len(q)>=10:raise HTTPException(429,'Слишком много обращений. Повторите через минуту.')
        q.append(now)

    def get(ticket_id: str):
        try:return store.get(ticket_id)
        except Missing:raise HTTPException(404,'Ticket not found') from None

    def conflict(fn,*args):
        try:return fn(*args)
        except Missing:raise HTTPException(404,'Ticket not found') from None
        except Conflict as exc:raise HTTPException(409,str(exc)) from None

    def analyse(data, topic=None):
        """Run the assistant and record how: time, mode and rules version travel with the result."""
        started = time.perf_counter()
        result = service.triage(data) if service.rules.rules else safe_fallback(topic)
        info = describe_service(service)
        result['meta'] = {'ms': round((time.perf_counter() - started) * 1000, 2), 'mode': info['mode'],
                          'rules_version': info['rules_version'], 'analysed_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
        return result

    def safe_fallback(topic=None):
        # This is a player-selected topic, not a model prediction or validated finding.
        category={'question':'report.question','complaint':'complaint.other',
                  'technical':'report.help','payment':'report.payment',
                  'account':'report.account','idea':'report.question'}.get(topic,'unclassified')
        return {'category':category,'priority':'p0' if topic in ('account','payment') else 'p2','lang':'und','needs_human':True,
                'confidence':0.0,'is_spam_or_duplicate':False,
                'reasons':['rules_unavailable','manual_triage_required']+(['topic_selected_by_player'] if topic else []),
                'extracted':{'nickname':None,'rule_refs':[],'has_evidence':False,'claims':[]},
                'draft_reply':{'text':'Ваше обращение принято. Специалист проверит его и при необходимости запросит дополнительные сведения.','lang':'ru','cited':[]}}

    @router.post('/support/tickets',status_code=201)
    def submit(payload: TicketCreate,request: Request):
        guard(request.client.host if request.client else 'unknown')
        data=payload.request
        if len(data.messages)!=1 or data.messages[0].role!='player' or not data.messages[0].text.strip():
            raise HTTPException(422,'One nonempty player message required')
        # The portal uploads files after ticket creation; selected files are not yet evidence.
        data = data.model_copy(update={'images_count': 0, 'messages': [
            message.model_copy(update={'attachments': 0}) for message in data.messages]})
        # This is a synthetic service, not an official Grand Mobile delivery.
        result=analyse(data,payload.topic)
        if data.kind=='complaint' or result['category'] in ('report.payment','report.account','complaint.admin'):
            result['needs_human']=True
        try:
            ticket,token=store.create(data.model_dump(),result)
            if getattr(service,'can_auto_close',None) and service.can_auto_close(result,data):
                ticket=store.auto_close_verified_faq(ticket['id'])
        except Conflict as exc:raise HTTPException(409,str(exc)) from None
        return {'id':ticket['id'],'access_token':token,'status':ticket['status'],'created_at':ticket['created_at'],
                'result':result,'notice':'Локальная платформа Outsiders: обращение не отправляется автоматически в Grand Mobile.'}

    async def upload(ticket_id: str, file: UploadFile = File(...), x_ticket_token: str | None = Header(default=None)):
        if not x_ticket_token:raise HTTPException(404,'Ticket not found')
        try:source_ticket=store.public_get(ticket_id,x_ticket_token)
        except Missing:raise HTTPException(404,'Ticket not found') from None
        try:
            from PIL import Image, ImageOps, UnidentifiedImageError
        except ImportError:
            raise HTTPException(503,'Загрузка изображений недоступна: установите Pillow (pip install Pillow).') from None
        raw=await file.read(5*1024*1024+1)
        await file.close()
        if len(raw)>5*1024*1024:raise HTTPException(413,'Максимум 5 МБ на изображение.')
        try:
            with Image.open(io.BytesIO(raw)) as initial:
                if initial.format not in ('PNG','JPEG','WEBP') or initial.width*initial.height>20_000_000:
                    raise ValueError('Unsupported image')
                initial.verify()
            with Image.open(io.BytesIO(raw)) as image:
                image=ImageOps.exif_transpose(image)
                out=io.BytesIO()
                if image.mode in ('RGBA','LA') or ('transparency' in image.info):
                    image.save(out,format='PNG',optimize=True);media_type='image/png'
                else:
                    image.convert('RGB').save(out,format='JPEG',quality=85,optimize=True);media_type='image/jpeg'
                clean=out.getvalue()
        except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError):
            raise HTTPException(415,'Поддерживаются только корректные JPG, PNG и WebP.') from None
        if len(clean)>10*1024*1024:raise HTTPException(413,'Изображение слишком большое после обработки.')
        path=uploads / secrets.token_hex(24)
        try:
            with path.open('xb') as f:f.write(clean)
            os.chmod(path,0o600)
            def refresh_attachment(data):
                from copy import deepcopy
                result = service.triage(data) if service.rules.rules else deepcopy(source_ticket['result'])
                result['extracted']['has_evidence'] = data['images_count'] > 0
                if data['kind'] == 'complaint':
                    result['needs_human'] = True
                return result
            return store.add_attachment(ticket_id,str(path),media_type,len(clean),refresh_attachment)
        except (Conflict,Missing) as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(409 if isinstance(exc,Conflict) else 404,str(exc)) from None
        except Exception:
            path.unlink(missing_ok=True)
            raise

    if _multipart_available():   # FastAPI refuses to start a file-upload route without python-multipart
        router.post('/support/tickets/{ticket_id}/attachments',status_code=201)(upload)

    @router.get('/support/tickets/{ticket_id}')
    def public_status(ticket_id: str,x_ticket_token: str | None = Header(default=None)):
        if not x_ticket_token:raise HTTPException(404,'Ticket not found')
        try:item=store.public_get(ticket_id,x_ticket_token)
        except Missing:raise HTTPException(404,'Ticket not found') from None
        return {'id':item['id'],'status':item['status'],'created_at':item['created_at'],'updated_at':item['updated_at']}

    @router.post('/admin/api/setup', status_code=201)
    def setup_first_operator(credentials: Login, request: Request, response: Response):
        # Setup is available only on the local machine, before any credentials exist.
        host = request.client.host if request.client else ''
        if host not in ('127.0.0.1', '::1', 'testclient'):
            raise HTTPException(403, 'Setup is only available on this computer')
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'Origin not allowed')
        config_path = os.getenv('GRAND_OPERATOR_CONFIG')
        if not config_path or auth.configured() or Path(config_path).exists():
            raise HTTPException(409, 'Operator setup is already complete or unavailable')
        try:
            write_config(config_path, credentials.password)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        # Successful first run directly signs in instead of asking for the password twice.
        cookie = auth.issue()
        response.set_cookie(auth.COOKIE, cookie, httponly=True, samesite='strict',
                            secure=(request.url.scheme == 'https'), max_age=auth.SESSION_TTL, path='/')
        return {'ok': True}

    @router.post('/admin/api/login')
    def login(credentials: Login,request: Request,response: Response):
        auth.check_password(credentials.password,request.client.host if request.client else 'unknown')
        cookie=auth.issue()
        response.set_cookie(auth.COOKIE,cookie,httponly=True,samesite='strict',secure=(request.url.scheme=='https' or os.getenv('GRAND_SECURE_COOKIES')=='1'),max_age=auth.SESSION_TTL,path='/')
        return {'ok':True,'csrf':auth.csrf(cookie)}

    @router.get('/admin/api/status')
    def assistant_status(request: Request):
        admin(request)
        return describe_service(service)

    @router.post('/admin/api/selftest')
    def selftest(request: Request):
        """Run the assistant on fixed sample tickets (nothing is stored) so the operator can see it working."""
        admin(request, True)
        info = describe_service(service)
        if not info['rules_loaded']:
            return {'status': info, 'results': [], 'error': 'Правила не загружены: помощник работает в ручном режиме.'}
        out = []
        for kind, text in SELFTEST_TEXTS:
            request_model = TriageRequest.model_validate({'kind': kind, 'messages': [{'role': 'player', 'text': text}], 'images_count': 1 if kind == 'complaint' else 0})
            started = time.perf_counter()
            result = service.triage(request_model)
            out.append({'text': text, 'kind': kind, 'lang': result['lang'], 'category': result['category'], 'priority': result['priority'],
                        'needs_human': result['needs_human'], 'confidence': result['confidence'],
                        'cited': [c['ref'] for c in result['draft_reply']['cited']], 'ms': round((time.perf_counter() - started) * 1000, 2)})
        return {'status': info, 'results': out}

    @router.post('/admin/api/rules')
    def load_rules(request: Request, body: dict = Body(...)):
        """Let the operator load the game rules file from the panel; it is saved locally and used at once."""
        admin(request, True)
        from app.rules import RuleIndex
        try:
            index = RuleIndex.from_data(body)
        except (KeyError, TypeError, ValueError):
            raise HTTPException(422, 'Это не файл правил Grand Mobile (rules.json). Выберите файл из пакета организаторов.') from None
        if not index.rules:
            raise HTTPException(422, 'В файле нет ни одного пункта правил.')
        target = Path(os.environ.get('GRAND_DB_PATH', 'data/support.sqlite3')).parent / 'rules.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        import json
        target.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
        service.rules = index
        return describe_service(service)

    @router.post('/admin/api/logout')
    def logout(request: Request,response: Response):
        admin(request,True);response.delete_cookie(auth.COOKIE,path='/');return {'ok':True}

    @router.get('/admin/api/session')
    def session(request: Request):
        admin(request)
        return {'operator':'operator','csrf':auth.csrf(auth.session(request))}

    @router.get('/admin/api/tickets')
    def ticket_list(request: Request,q: str='',status: str='',priority: str='',limit: int=Query(80,ge=1,le=200),offset:int=Query(0,ge=0),human: bool=False):
        admin(request)
        if status and status not in ('new','in_review','needs_info','escalated','resolved','closed'):raise HTTPException(422,'Invalid status')
        if priority and priority not in ('p0','p1','p2','p3','urgent'):raise HTTPException(422,'Invalid priority')
        return store.list(q,status,priority,limit,offset,human)

    @router.get('/admin/api/tickets/{ticket_id}')
    def ticket_detail(ticket_id:str,request:Request):admin(request);return get(ticket_id)

    @router.get('/admin/api/tickets/{ticket_id}/attachments')
    def attachments(ticket_id: str,request:Request):
        admin(request)
        try:return {'items':store.list_attachments(ticket_id)}
        except Missing:raise HTTPException(404,'Ticket not found') from None

    @router.get('/admin/api/tickets/{ticket_id}/attachments/{attachment_id}')
    def download(ticket_id: str,attachment_id:str,request:Request):
        admin(request)
        try:attachment=store.attachment(ticket_id,attachment_id)
        except Missing:raise HTTPException(404,'Attachment not found') from None
        return FileResponse(attachment['path'],media_type=attachment['content_type'],filename=attachment['filename'],
                            content_disposition_type='attachment',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @router.get('/admin/api/tickets/{ticket_id}/audit')
    def audit(ticket_id:str,request:Request):
        admin(request)
        try:return {'events':store.audit(ticket_id)}
        except Missing:raise HTTPException(404,'Ticket not found') from None

    @router.post('/admin/api/tickets')
    def create_internal(payload: TicketCreate,request:Request):
        admin(request,True)
        data=payload.request
        if not any(m.text.strip() for m in data.messages if m.role=='player'):
            raise HTTPException(422,'Empty player message')
        result=analyse(data,payload.topic)
        if data.kind=='complaint' or result['category'] in ('report.payment','report.account','complaint.admin'):
            result['needs_human']=True
        try:
            item,_=store.create(data.model_dump(),result,source='operator')
            if getattr(service,'can_auto_close',None) and service.can_auto_close(result,data):
                item=store.auto_close_verified_faq(item['id'])
        except Conflict as exc:raise HTTPException(409,str(exc)) from None
        return item

    @router.put('/admin/api/tickets/{ticket_id}/draft')
    def edit(ticket_id:str,payload:DraftEdit,request:Request):
        actor=admin(request,True)
        return conflict(store.edit_draft,ticket_id,payload.version,payload.text,actor)

    @router.post('/admin/api/tickets/{ticket_id}/verify')
    def verify(ticket_id:str,payload:Version,request:Request):
        actor=admin(request,True);item=get(ticket_id)
        if item['version']!=payload.version:raise HTTPException(409,'Ticket changed; reload')
        if not service.rules.rules:raise HTTPException(503,'Правила не загружены. Нажмите на статус помощника вверху и загрузите файл rules.json.')
        try:
            triage_request=TriageRequest.model_validate(item['request'])
            draft={**item['result']['draft_reply'],'text':item['draft_text']}
            if getattr(service,'team_classifier',None) is not None:
                from app.hybrid import check_operator_reply
                checked,reasons=check_operator_reply(draft,service.rules,triage_request,item['result']['category'],item['result']['lang'])
            else:
                checked,reasons=check_draft(draft,service.rules,triage_request,item['result']['category'],item['result']['lang'],item['result']['extracted']['has_evidence'])
        except (ValueError, KeyError):raise HTTPException(422,'Draft or source data invalid') from None
        if reasons:return {'approved':False,'reasons':reasons,'ticket':item}
        result=conflict(store.approve_draft,ticket_id,payload.version,actor)
        return {'approved':True,'reasons':[],'ticket':result}

    @router.post('/admin/api/tickets/{ticket_id}/status')
    def change_status(ticket_id:str,payload:Mutation,request:Request):
        actor=admin(request,True)
        return conflict(store.set_status,ticket_id,payload.version,payload.status,actor,payload.note)

    return router
