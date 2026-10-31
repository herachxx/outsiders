"""SQLite ticket repository. No customer data is stored in browser localStorage.

Each request opens its own connection and all writes use optimistic versioning.
Only this module touches the database. Serialized fields are JSON, not pickle.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

STATES = ('new', 'in_review', 'needs_info', 'escalated', 'resolved', 'closed')
TRANSITIONS = {
    'new': {'in_review', 'escalated', 'needs_info'},
    'in_review': {'needs_info', 'escalated', 'resolved'},
    'needs_info': {'in_review', 'escalated'},
    'escalated': {'in_review', 'resolved'},
    'resolved': {'closed', 'in_review'},
    'closed': {'in_review'},
}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def fingerprint(request: dict) -> str:
    # Identifier-free exact deduplication. Does not include responses from admins.
    fields = {'kind': request.get('kind'), 'region': request.get('region'),
              'nick': request.get('reported_nick'),
              'text': ' '.join(' '.join(m.get('text', '').casefold().split()) for m in request.get('messages', []) if m.get('role') == 'player')}
    fields['reporter_hash'] = request.get('reporter_hash')
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class Conflict(Exception):
    pass


class Missing(Exception):
    pass


class TicketStore:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript('''
            CREATE TABLE IF NOT EXISTS tickets (
                id TEXT PRIMARY KEY,
                access_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                request_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                draft_text TEXT NOT NULL DEFAULT '',
                draft_approved INTEGER NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 1,
                assigned_to TEXT NOT NULL DEFAULT '',
                reviewer_note TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS ix_tickets_order ON tickets(status, created_at DESC);
            CREATE INDEX IF NOT EXISTS ix_tickets_created ON tickets(created_at DESC);
            CREATE INDEX IF NOT EXISTS ix_tickets_fingerprint ON tickets(fingerprint, created_at);
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                occurred_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS ix_audit_ticket ON audit(ticket_id, id);
            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL, filename TEXT NOT NULL, content_type TEXT NOT NULL,
                size INTEGER NOT NULL, path TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_attachments_ticket ON attachments(ticket_id);
            ''')

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=10000')
        conn.execute('PRAGMA journal_mode=WAL')
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def hydrate(row: sqlite3.Row) -> dict:
        result = dict(row)
        result['request'] = json.loads(result.pop('request_json'))
        result['result'] = json.loads(result.pop('result_json'))
        result['draft_approved'] = bool(result['draft_approved'])
        result.pop('access_hash', None)
        result.pop('fingerprint', None)
        return result

    def create(self, request: dict, result: dict, source: str = 'player') -> tuple[dict, str]:
        now = utc()
        access_token = secrets.token_urlsafe(32)
        ticket_id = 'GM-' + secrets.token_hex(5).upper()
        digest = fingerprint(request)
        draft = result.get('draft_reply', {}).get('text', '')
        with self.connect() as conn:
            # Exact duplicate detection only: do not expose another ticket's details.
            existing = conn.execute('SELECT 1 FROM tickets WHERE fingerprint=? AND created_at>=? LIMIT 1',
                                    (digest, (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(timespec='seconds'))).fetchone()
            if existing and request.get('reporter_hash'):
                raise Conflict('Похожее обращение уже зарегистрировано за последний час.')
            conn.execute('''INSERT INTO tickets
                (id,access_hash,created_at,updated_at,request_json,result_json,fingerprint,draft_text)
                VALUES (?,?,?,?,?,?,?,?)''',
                (ticket_id, hashlib.sha256(access_token.encode()).hexdigest(), now, now,
                 json.dumps(request, ensure_ascii=False), json.dumps(result, ensure_ascii=False), digest, draft))
            self._audit(conn, ticket_id, source, 'created', {'priority':result.get('priority')})
            row = conn.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
        return self.hydrate(row), access_token

    def auto_close_verified_faq(self, ticket_id: str) -> dict:
        # Atomic auto-resolution exclusively for an exact trusted platform-help FAQ.
        with self.connect() as conn:
            row=conn.execute('SELECT status,request_json,result_json,version FROM tickets WHERE id=?',(ticket_id,)).fetchone()
            if row is None:raise Missing()
            request=json.loads(row['request_json']);result=json.loads(row['result_json'])
            from app.hybrid import HybridTriageService
            from app.schemas import TriageRequest
            try:validated=TriageRequest.model_validate(request)
            except ValueError:raise Conflict('Некорректный запрос для автозакрытия') from None
            if row['status']!='new' or not HybridTriageService.can_auto_close(result,validated):
                raise Conflict('Обращение требует оператора')
            cur=conn.execute("UPDATE tickets SET status='closed',draft_approved=1,version=version+1, updated_at=? WHERE id=? AND version=? AND status='new'",(utc(),ticket_id,row['version']))
            if cur.rowcount!=1:raise Conflict('Обращение уже изменено')
            self._audit(conn,ticket_id,'system','auto_closed_verified_faq',{'reason':'verified_support_faq'})
        return self.get(ticket_id)

    def get(self, ticket_id: str) -> dict:
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
        if row is None:
            raise Missing()
        return self.hydrate(row)

    def public_get(self, ticket_id: str, token: str) -> dict:
        if len(token) > 300:
            raise Missing()
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM tickets WHERE id=?', (ticket_id,)).fetchone()
        if not row or not secrets.compare_digest(str(row['access_hash']), hashlib.sha256(token.encode()).hexdigest()):
            raise Missing()
        return self.hydrate(row)

    def list(self, q: str = '', status: str = '', priority: str = '', limit: int = 100, offset: int = 0, human: bool = False) -> dict:
        where, args = [], []
        if status:
            where.append('status=?'); args.append(status)
        if priority:
            if priority=='urgent':where.append("json_extract(result_json, '$.priority') IN ('p0','p1')")
            else:where.append("json_extract(result_json, '$.priority')=?");args.append(priority)
        if human:
            where.append("(json_extract(result_json, '$.needs_human')=1 OR status='escalated')")
        if q:
            # Limit search to sanitized user input, bind SQL parameters.
            q = q[:100].replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            like = f'%{q}%'
            where.append("(id LIKE ? ESCAPE '\\' OR request_json LIKE ? ESCAPE '\\')")
            args.extend((like,like))
        clause = (' WHERE '+' AND '.join(where)) if where else ''
        with self.connect() as conn:
            total = conn.execute('SELECT COUNT(*) FROM tickets'+clause,args).fetchone()[0]
            rows = conn.execute('''SELECT * FROM tickets'''+clause+'''
                ORDER BY CASE json_extract(result_json,'$.priority') WHEN 'p0' THEN 0 WHEN 'p1' THEN 1 WHEN 'p2' THEN 2 ELSE 3 END,
                created_at DESC LIMIT ? OFFSET ?''', (*args,limit,offset)).fetchall()
        return {'items':[self.hydrate(x) for x in rows], 'total':total, 'limit':limit,'offset':offset}

    @staticmethod
    def _audit(conn: sqlite3.Connection, ticket_id: str, actor: str, action: str, detail: dict | None = None):
        conn.execute('INSERT INTO audit(ticket_id,occurred_at,actor,action,detail) VALUES (?,?,?,?,?)',
                     (ticket_id,utc(),actor,action,json.dumps(detail or {},ensure_ascii=False)))

    def audit(self, ticket_id: str) -> list[dict]:
        self.get(ticket_id)
        with self.connect() as conn:
            rows = conn.execute('SELECT occurred_at,actor,action,detail FROM audit WHERE ticket_id=? ORDER BY id DESC LIMIT 100', (ticket_id,)).fetchall()
        return [{'occurred_at':x['occurred_at'],'actor':x['actor'],'action':x['action'],'detail':json.loads(x['detail'])} for x in rows]

    def edit_draft(self, ticket_id: str, version: int, text: str, actor: str):
        with self.connect() as conn:
            cur = conn.execute('''UPDATE tickets SET draft_text=?,draft_approved=0,updated_at=?,version=version+1
                WHERE id=? AND version=? AND status NOT IN ('resolved','closed')''',(text,utc(),ticket_id,version))
            if cur.rowcount != 1:
                self._conflict_or_missing(conn,ticket_id)
            self._audit(conn,ticket_id,actor,'draft_edited',{'length':len(text)})
        return self.get(ticket_id)

    def approve_draft(self, ticket_id: str, version: int, actor: str):
        with self.connect() as conn:
            cur=conn.execute('''UPDATE tickets SET draft_approved=1,updated_at=?,version=version+1 WHERE id=? AND version=?
                AND status NOT IN ('resolved','closed')''',(utc(),ticket_id,version))
            if cur.rowcount != 1:self._conflict_or_missing(conn,ticket_id)
            self._audit(conn,ticket_id,actor,'draft_verified')
        return self.get(ticket_id)

    def set_status(self, ticket_id: str, version: int, status: str, actor: str, note: str = ''):
        with self.connect() as conn:
            row=conn.execute('SELECT status,draft_approved,version FROM tickets WHERE id=?',(ticket_id,)).fetchone()
            if not row:raise Missing()
            if row['version']!=version:raise Conflict('Тикет изменился в другой вкладке. Обновите данные.')
            if status not in TRANSITIONS[row['status']]:raise Conflict('Недопустимый переход статуса.')
            if status=='resolved' and not row['draft_approved']:
                raise Conflict('Перед завершением подтвердите безопасность черновика.')
            cur=conn.execute('''UPDATE tickets SET status=?,reviewer_note=?,updated_at=?,version=version+1
                WHERE id=? AND version=?''',(status,note,utc(),ticket_id,version))
            if cur.rowcount!=1:raise Conflict('Обращение обновлено другим оператором.')
            self._audit(conn,ticket_id,actor,'status_changed',{'from':row['status'],'to':status,'note':note[:500]})
        return self.get(ticket_id)

    def _conflict_or_missing(self, conn, ticket_id):
        if not conn.execute('SELECT 1 FROM tickets WHERE id=?',(ticket_id,)).fetchone():raise Missing()
        raise Conflict('Обращение изменилось. Обновите его перед сохранением.')

    def add_attachment(self,ticket_id: str, path: str, content_type: str, size: int) -> dict:
        attachment_id='ATT-'+secrets.token_hex(10)
        ext='.jpg' if content_type=='image/jpeg' else '.png'
        with self.connect() as conn:
            if not conn.execute('SELECT 1 FROM tickets WHERE id=?',(ticket_id,)).fetchone():raise Missing()
            if conn.execute('SELECT COUNT(*) FROM attachments WHERE ticket_id=?',(ticket_id,)).fetchone()[0]>=4:
                raise Conflict('Не более четырёх вложений для одного обращения.')
            conn.execute('INSERT INTO attachments(id,ticket_id,created_at,filename,content_type,size,path) VALUES (?,?,?,?,?,?,?)',
                         (attachment_id,ticket_id,utc(),'screenshot'+ext,content_type,size,path))
            self._audit(conn,ticket_id,'player','attachment_added',{'attachment_id':attachment_id,'size':size})
        return {'id':attachment_id,'filename':'screenshot'+ext,'content_type':content_type,'size':size}

    def list_attachments(self,ticket_id: str) -> list[dict]:
        self.get(ticket_id)
        with self.connect() as conn:
            rows=conn.execute('SELECT id,filename,content_type,size,created_at FROM attachments WHERE ticket_id=? ORDER BY created_at,id',(ticket_id,)).fetchall()
        return [dict(row) for row in rows]

    def attachment(self,ticket_id: str,attachment_id: str) -> dict:
        with self.connect() as conn:
            row=conn.execute('SELECT * FROM attachments WHERE ticket_id=? AND id=?',(ticket_id,attachment_id)).fetchone()
        if not row:raise Missing()
        return dict(row)

    def purge(self, days: int = 14) -> int:
        if days < 1:raise ValueError("Retention must be at least one day")
        cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
        with self.connect() as conn:
            files=[row[0] for row in conn.execute('''SELECT path FROM attachments WHERE ticket_id IN
                   (SELECT id FROM tickets WHERE created_at<?)''',(cutoff,)).fetchall()]
            cur=conn.execute('DELETE FROM tickets WHERE created_at<?',(cutoff,))
        for file in files:
            try:os.unlink(file)
            except FileNotFoundError:pass
        return cur.rowcount
