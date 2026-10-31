"""Small single-operator cookie session. Requires explicit configuration."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict, deque
from fastapi import HTTPException, Request

from .local_config import read_config, verify_password

COOKIE='grand_operator'
SESSION_TTL=8*3600
LOGIN_ATTEMPTS=defaultdict(deque)


def _local():
    path = os.environ.get('GRAND_OPERATOR_CONFIG')
    return read_config(path) if path else None

def _secret() -> str:
    local = _local()
    return local['session_secret'] if local else os.environ.get('GRAND_SESSION_SECRET', '')

def configured() -> bool:
    local = _local()
    if local:
        return True
    if os.environ.get('GRAND_OPERATOR_CONFIG'):
        return False  # explicit config path that cannot be read; fail closed
    return bool(len(os.environ.get('GRAND_ADMIN_PASSWORD','')) >= 12 and len(os.environ.get('GRAND_SESSION_SECRET','')) >= 32)


def sign(data: str) -> str:
    secret=_secret().encode()
    return hmac.new(secret,data.encode(),hashlib.sha256).hexdigest()


def issue() -> str:
    payload={'sub':'operator','exp':int(time.time())+SESSION_TTL,'nonce':secrets.token_hex(12)}
    data=base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':')).encode()).decode().rstrip('=')
    return data+'.'+sign(data)


def session(request: Request) -> str | None:
    if not configured():return None
    cookie=request.cookies.get(COOKIE,'')
    try:
        data,signature=cookie.split('.',1)
        if len(data)>500 or not hmac.compare_digest(sign(data),signature):return None
        obj=json.loads(base64.urlsafe_b64decode(data+'==='))
        if obj.get('sub')=='operator' and int(obj['exp'])>time.time():return cookie
    except (ValueError,KeyError,TypeError):pass
    return None


def csrf(cookie: str) -> str:
    return hmac.new(_secret().encode(),('csrf:'+cookie).encode(),hashlib.sha256).hexdigest()


def ensure_admin(request: Request, unsafe: bool = False) -> str:
    if not configured():raise HTTPException(503,'Operator login not configured')
    cookie=session(request)
    if not cookie:raise HTTPException(401,'Operator authentication required')
    if unsafe:
        supplied=request.headers.get('X-CSRF-Token','')
        if not hmac.compare_digest(csrf(cookie),supplied):raise HTTPException(403,'CSRF check failed')
        # An origin mismatch is blocked even if a token was somehow attached.
        origin=request.headers.get('origin')
        if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
            raise HTTPException(403,'Cross-origin operation blocked')
    return 'operator'


def check_password(password: str, host: str) -> None:
    if not configured():raise HTTPException(503,'Operator login not configured')
    now=time.monotonic()
    times=LOGIN_ATTEMPTS[host]
    while times and times[0]<now-900:times.popleft()
    if len(times)>=7:raise HTTPException(429,'Too many attempts. Try again later.')
    local = _local()
    if local:
        valid = verify_password(password, local['password'])
    else:
        expected = os.environ['GRAND_ADMIN_PASSWORD']
        valid = hmac.compare_digest(hashlib.sha256(password.encode()).digest(),hashlib.sha256(expected.encode()).digest())
    if not valid:
        times.append(now)
        raise HTTPException(401,'Invalid credentials')
    times.clear()
